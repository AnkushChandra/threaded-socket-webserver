from socket import *
from socket import timeout
import os
from email.utils import formatdate
import threading
import argparse
import sys

BASE_THREADS = threading.active_count()

# function computes the timeout in case for HTTP/1.1
def computeTimeout():
    active = max(1, threading.active_count() - BASE_THREADS)
    min_timeout = 2
    max_timeout = 10

    if active <= 1:
        timeout = 5
    elif active <= 3:
        timeout = 3
    else:
        timeout = 3 - 1 * (active - 3)

    return max(min_timeout, min(max_timeout, timeout))

# function to send a response back to client
def sendResponse(sock, http_version, code, reason, headers, body):
    
    status = f"{http_version} {code} {reason}"
    lines=[status]
    
    for k,v in headers.items():
        lines.append(f"{k}: {v}")
    lines.append(f"Date: {formatdate(usegmt=True)}")
    lines.append("")

    raw = ("\r\n".join(lines)+ "\r\n").encode()

    try:
        sock.sendall(raw)
        sock.sendall(body)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass

# function to assign the file type MIME to the file
def getContentType(path):
    ext = path.rsplit(".")[-1].lower()
    return {
        "html":"text/html", "htm":"text/html", "txt":"text/plain",
        "css":"text/css", "js":"application/javascript",
        "png":"image/png", "jpg":"image/jpeg", "jpeg":"image/jpeg",
        "gif":"image/gif", "svg":"image/svg+xml", "ico":"image/x-icon",
        "woff":"font/woff", "woff2":"font/woff2", "mp4":"video/mp4",
    }.get(ext, "application/octet-stream")

# function to extract the function request head to check for HTTP version and request type
def getRequestHead(cSocket, buf=b""):
    while True:
        i = buf.find(b"\r\n\r\n")
        if i != -1:

            return buf[:i+4], buf[i+4:]
        j = buf.find(b"\n\n")
        if j != -1:

            return buf[:j+2], buf[j+2:]
        try:
            chunk = cSocket.recv(4096)
        except timeout:             
            return (None, b"")
        except (ConnectionResetError, BrokenPipeError, OSError):
            return (None, b"")

        if not chunk:
            return (None, b"") 
        buf += chunk

# function to extract file path , method, version of http
def parseHead(head):
    head = head.decode()
    lines=head.split("\r\n")
    if len(lines) == 1:
        lines = head.split("\n")
    
    requestLine=lines[0].strip()
    print(requestLine)
    requestSplit=requestLine.split()

    if len(requestSplit) == 3:
        method=requestSplit[0]
        target=requestSplit[1]
        filePath = target.split('#', 1)[0]  
        filePath = filePath.split('?', 1)[0] 
        version=requestSplit[2]
    else:
        return None
    headers = {}

    for line in lines[1:]:
        if ':' in line:
            k,v = line.split(":", 1)

            headers[k.strip().lower()] = v.strip()
    return method, target, version, headers

def versionCheck(version):
    if version == "HTTP/1.1":
        return True
    if version == "HTTP/1.0":
        return False
    return False

# function to serve the file from the local directory
def servePath(sock, version, target, ka):
    path_only = target.split("#", 1)[0].split("?", 1)[0]
    if path_only=="/":
        path_only="/index.html"
    
    rel = path_only.lstrip('/')

    fullPath= os.path.join(DOCROOT, rel)

    if os.path.isfile(fullPath):
        try:
            with open(fullPath, 'rb') as f:
                body = f.read()
                
                headers={
                    "Content-Length": str(len(body)),
                    "Content-Type": getContentType(fullPath)
                }
                
                sendResponse(sock,version, 200 , "OK", headers, body)
                
            print("RESOLVED:", fullPath, "(OK)")
        except PermissionError:
            body = b"<html><body><h1>403 Forbidden</h1></body></html>"
            headers = {
                "Content-Type": "text/html",
                "Content-Length": str(len(body)),
            }
            sendResponse(sock,version, 403 , "Forbidden", headers, body)
            print("RESOLVED:", fullPath, "(FORBIDDEN)")
        except FileNotFoundError:
            body = b"<html><body><h1>404 Not Found</h1></body></html>"
            headers = {
                "Content-Type": "text/html",
                "Content-Length": str(len(body)),
            }
            sendResponse(sock,version, 404 , "Not Found", headers, body)
            print("RESOLVED:", fullPath, "(NOT FOUND)")
    else:
        body = b"<html><body><h1>404 Not Found</h1></body></html>"
        headers = {
                "Content-Type": "text/html",
                "Content-Length": str(len(body)),
            }
        sendResponse(sock,version, 404 , "Not Found", headers, body)
        print("RESOLVED:", fullPath, "(NOT FOUND)")
    return ka


# function to handle the client request and send response

def handleClient(cSocket,addr):
    
    print("*********")
    buf = b""

    cSocket.settimeout(None)
    while True:
        requestHead, buf= getRequestHead(cSocket,buf)

        if requestHead is None:
            break
        parsed = parseHead(requestHead)


        if not parsed:
            body = b"<html><body><h1>400 Bad Request</h1></body></html>"
            hdrs = {"Content-Type": "text/html", "Content-Length": str(len(body)), "Connection": "close"}
            sendResponse(cSocket, "HTTP/1.1", 400, "Bad Request", hdrs, body)
            break


        method, target, version, headers= parsed
        

        if method.upper() != "GET":
            body = b"<html><body><h1>400 Bad Request</h1></body></html>"
            hdrs = {"Content-Type": "text/html", "Content-Length": str(len(body)), "Connection": "close"}
            sendResponse(cSocket, version, 400, "Bad Request", hdrs, body)
            break

        aliveCheck = versionCheck(version)

        cont= servePath(cSocket,version,target, aliveCheck)
        
        # the functionality to check to close the connetion or not based on HTTP/1.0 or HTTP/1.1
        # cont - variable to check whther to continue or close the connection
        if not cont:
            break
        t = computeTimeout()
        cSocket.settimeout(t)

    cSocket.close()


if __name__=='__main__':
    
    DOCROOT = os.getcwd()
    serverPort = 8888

    args = sys.argv[1:]
    for i in range(0, len(args),2):

        if args[i] =="--document_root" and i + 1 < len(args):
            DOCROOT = os.path.abspath(args[i + 1])
        elif args[i] == "--port" and i + 1 < len(args):
            serverPort = int(args[i + 1])
        else:
            print("Usage: python server.py --document_root PATH --port PORT")
            sys.exit(2)

    #initialise socket
    serverSocket= socket(AF_INET,SOCK_STREAM)
    serverSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    serverSocket.bind(('',serverPort))
    serverSocket.listen(128)

    while True:
        cSocket, addr= serverSocket.accept()
        
        t1=threading.Thread(target=handleClient, args=(cSocket,addr))
        t1.start()
        #handleClient(cSocket)

