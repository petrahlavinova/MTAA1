
#    Copyright 2014 Philippe THIRION
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import socketserver
import re
import string
import socket
import sys
import time
import logging

logging.basicConfig(format='%(asctime)s:%(levelname)s:%(message)s',filename='proxy.log',level=logging.INFO,datefmt='%H:%M:%S')

HOST, PORT = '0.0.0.0', 5060
rx_register = re.compile("^REGISTER")
rx_invite = re.compile("^INVITE")
rx_ack = re.compile("^ACK")
rx_prack = re.compile("^PRACK")
rx_cancel = re.compile("^CANCEL")
rx_bye = re.compile("^BYE")
rx_options = re.compile("^OPTIONS")
rx_subscribe = re.compile("^SUBSCRIBE")
rx_publish = re.compile("^PUBLISH")
rx_notify = re.compile("^NOTIFY")
rx_info = re.compile("^INFO")
rx_message = re.compile("^MESSAGE")
rx_refer = re.compile("^REFER")
rx_update = re.compile("^UPDATE")
rx_from = re.compile("^From:")
rx_cfrom = re.compile("^f:")
rx_to = re.compile("^To:")
rx_cto = re.compile("^t:")
rx_id = re.compile("^Call-ID:")
rx_tag = re.compile(";tag")
rx_contact = re.compile("^Contact:")
rx_ccontact = re.compile("^m:")
rx_uri = re.compile("sip:([^@]*)@([^;>$]*)")
rx_addr = re.compile("sip:([^ ;>$]*)")
rx_code = re.compile("^SIP/2.0 ([^ ]*)")
rx_request_uri = re.compile("^([^ ]*) sip:([^ ]*) SIP/2.0")
rx_route = re.compile("^Route:")
rx_contentlength = re.compile("^Content-Length:")
rx_ccontentlength = re.compile("^l:")
rx_via = re.compile("^Via:")
rx_cvia = re.compile("^v:")
rx_branch = re.compile(";branch=([^;]*)")
rx_rport = re.compile(";rport$|;rport;")
rx_contact_expires = re.compile("expires=([^;$]*)")
rx_expires = re.compile("^Expires: (.*)$")

rx_cseqInvite = re.compile("^CSeq: \d* INVITE")
rx_200 = re.compile("^SIP/2.0 200")
rx_603 = re.compile("^SIP/2.0 603")
rx_subject = re.compile("^Subject:")

# global dictionnary
recordroute = ""
topvia = ""
registrar = {}

def hexdump( chars, sep, width ):
    while chars:
        line = chars[:width]
        chars = chars[width:]
        line = line.ljust( width, '\000' )

def prepare():
    global recordroute,topvia
    hostname = socket.gethostname()
    ipaddress = socket.gethostbyname(hostname)
    if ipaddress == "127.0.0.1":
        ipaddress = sys.argv[1]
    recordroute = "Record-Route: <sip:%s:%d;lr>" % (ipaddress,PORT)
    topvia = "Via: SIP/2.0/UDP %s:%d" % (ipaddress,PORT)


def quotechars( chars ):
	return ''.join( ['.', c][c.isalnum()] for c in chars )


class UDPHandler(socketserver.BaseRequestHandler):   
    
    def changeRequestUri(self):
        # change request uri
        md = rx_request_uri.search(self.data[0])
        if md:
            method = md.group(1)
            uri = md.group(2)
            if uri in registrar:
                uri = "sip:%s" % registrar[uri][0]
                self.data[0] = "%s %s SIP/2.0" % (method,uri)
        
    def removeRouteHeader(self):
        # delete Route
        data = []
        for line in self.data:
            if not rx_route.search(line):
                data.append(line)
        return data
    
    def addTopVia(self):
        branch= ""
        data = []
        for line in self.data:
            if rx_via.search(line) or rx_cvia.search(line):
                md = rx_branch.search(line)
                if md:
                    branch=md.group(1)
                    via = "%s;branch=%sm" % (topvia, branch)
                    data.append(via)
                # rport processing
                if rx_rport.search(line):
                    text = "received=%s;rport=%d" % self.client_address
                    via = line.replace("rport",text)   
                else:
                    text = "received=%s" % self.client_address[0]
                    via = "%s;%s" % (line,text)
                data.append(via)
            else:
                data.append(line)
        return data
                
    def removeTopVia(self):
        data = []
        for line in self.data:
            if rx_via.search(line) or rx_cvia.search(line):
                if not line.startswith(topvia):
                    data.append(line)
            else:
                data.append(line)
        return data
    
    def getSocketInfo(self,uri):
        addrport, socket, client_addr = registrar[uri]
        return (socket,client_addr)
        
    def getDestination(self):
        destination = ""
        for line in self.data:
            if rx_to.search(line) or rx_cto.search(line):
                md = rx_uri.search(line)
                if md:
                    destination = "%s@%s" %(md.group(1),md.group(2))
                break
        return destination

    def getCallId(self):
        callId = ""
        for line in self.data:
            if rx_id.search(line):
                callId = line[9:]
                break
        return callId

    def isInvite(self):
        for line in self.data:
            if rx_cseqInvite.search(line):
                return True
        return False

    def isOk(self):
        if rx_200.search(self.data[0]):
            return True
        return False

    def isDeclined(self):
        if rx_603.search(self.data[0]):
            return True
        return False

    def hasSubject(self):
        for line in self.data:
            if rx_subject.search(line):
                return True
        return False

    def getOrigin(self):
        origin = ""
        for line in self.data:
            if rx_from.search(line) or rx_cfrom.search(line):
                md = rx_uri.search(line)
                if md:
                    origin = "%s@%s" %(md.group(1),md.group(2))
                break
        return origin
        
    def sendResponse(self,code):
        request_uri = "SIP/2.0 " + code
        self.data[0]= request_uri
        index = 0
        data = []
        for line in self.data:
            data.append(line)
            if rx_to.search(line) or rx_cto.search(line):
                if not rx_tag.search(line):
                    data[index] = "%s%s" % (line,";tag=123456")
            if rx_via.search(line) or rx_cvia.search(line):
                # rport processing
                if rx_rport.search(line):
                    text = "received=%s;rport=%d" % self.client_address
                    data[index] = line.replace("rport",text) 
                else:
                    text = "received=%s" % self.client_address[0]
                    data[index] = "%s;%s" % (line,text)      
            if rx_contentlength.search(line):
                data[index]="Content-Length: 0"
            if rx_ccontentlength.search(line):
                data[index]="l: 0"
            index += 1
            if line == "":
                break
        data.append("")
        text = "\r\n".join(data)
        self.socket.sendto(text.encode('utf-8'),self.client_address)
        
    def processRegister(self):
        global registrar
        fromm = ""
        contact = ""
        for line in self.data:
            if rx_to.search(line) or rx_cto.search(line):
                md = rx_uri.search(line)
                if md:
                    fromm = "%s@%s" % (md.group(1),md.group(2))
            if rx_contact.search(line) or rx_ccontact.search(line):
                md = rx_uri.search(line)
                if md:
                    contact = md.group(2)
                else:
                    md = rx_addr.search(line)
                    if md:
                        contact = md.group(1)
            
        logging.info(f"Registracia uzivatela: {fromm} ({contact})")
        registrar[fromm]=[contact,self.socket,self.client_address]
        self.sendResponse("200 0K / V poriadku")
        
    def processInvite(self):
        origin = self.getOrigin()
        if len(origin) == 0 or not origin in registrar:
            self.sendResponse("400 Bad Request/ Neplatny host")
            return
        destination = self.getDestination()
        cSubject = self.hasSubject()
        if not cSubject:
            callId = self.getCallId()
            logging.info(f"[ID: {callId}] Hovor bol vytoceny: {origin} -> {destination}")
        if len(destination) > 0:
            if destination in registrar:
                socket,claddr = self.getSocketInfo(destination)
                self.data = self.addTopVia()
                data = self.removeRouteHeader()
                data.insert(1,recordroute)
                text = "\r\n".join(data)
                socket.sendto(text.encode('utf-8') , claddr)
            else:
                self.sendResponse("480 Temporarily Unavailable / Neregistrovany ucastnik")
        else:
            self.sendResponse("500 Server Internal Error / Nespravny ciel")
                
    def processAck(self):
        destination = self.getDestination()
        if len(destination) > 0:
            if destination in registrar:
                socket,claddr = self.getSocketInfo(destination)
                #self.changeRequestUri()
                self.data = self.addTopVia()
                data = self.removeRouteHeader()
                #insert Record-Route
                data.insert(1,recordroute)
                text = "\r\n".join(data)
                socket.sendto(text.encode('utf-8'),claddr)
                
    def processNonInvite(self):
        origin = self.getOrigin()
        if len(origin) == 0 or not origin in registrar:
            self.sendResponse("400 Bad Request/ Neplatny host")
            return
        destination = self.getDestination()
        if len(destination) > 0:
            if destination in registrar:
                socket,claddr = self.getSocketInfo(destination)
                #self.changeRequestUri()
                self.data = self.addTopVia()
                data = self.removeRouteHeader()
                #insert Record-Route
                data.insert(1,recordroute)
                text = "\r\n".join(data)
                socket.sendto(text.encode('utf-8') , claddr)
            else:
                self.sendResponse("406 Not Acceptable / Neregistrovany ucastnik")
        else:
            self.sendResponse("500 Server Internal Error / Nespravny ciel")
                
    def processCode(self):
        origin = self.getOrigin()
        cSeq = self.isInvite()
        cOk = self.isOk()
        cDeclined = self.isDeclined()
        statusCode = int(rx_code.search(self.data[0]).group(1))
        if len(origin) > 0:
            if origin in registrar:
                socket,claddr = self.getSocketInfo(origin)
                self.data = self.removeRouteHeader()
                data = self.removeTopVia()
                if cSeq and cOk:
                    destination = self.getDestination()
                    callId = self.getCallId()
                    logging.info(f"[ID :{callId}] Hovor bol prijaty: {origin} <- {destination}")
                if cSeq and cDeclined:
                    destination = self.getDestination()
                    callId = self.getCallId()
                    logging.info(f"[ID :{callId}] Hovor bol odmietnuty: {origin} <- {destination}")
                if statusCode == 100:
                    data[0] = 'SIP/2.0 100 Snazim sa nadviazat spojenie'
                elif statusCode == 180:
                    data[0] = 'SIP/2.0 180 Zvonim' 
                elif statusCode == 181:
                    data[0] = 'SIP/2.0 181 Hovor je presmerovany' 
                elif statusCode == 408:
                    data[0] = 'SIP/2.0 408 Casovy limit vyprsal' 
                elif statusCode == 486:
                    data[0] = 'SIP/2.0 486 Obsadene'
                elif statusCode == 487:
                    data[0] = 'SIP/2.0 487 Ziados?? zrusena'
                elif statusCode == 503:
                    data[0] = 'SIP/2.0 503 Nedostupna sluzba' 
                elif statusCode == 504:
                    data[0] = 'SIP/2.0 504 Casovy limit servera vyprsal'
                elif statusCode == 603:
                    data[0] = 'SIP/2.0 603 Zamietnute' 
                text = "\r\n".join(data)
                socket.sendto(text.encode('utf-8'),claddr)  
                
    def processRequest(self):
        #print "processRequest"
        if len(self.data) > 0:
            request_uri = self.data[0]
            if rx_register.search(request_uri):
                self.processRegister()
            elif rx_invite.search(request_uri):
                self.processInvite()
            elif rx_ack.search(request_uri):
                self.processAck()
            elif rx_bye.search(request_uri):
                self.processNonInvite()
                origin = self.getOrigin()
                destination = self.getDestination()
                callId = self.getCallId()
                logging.info(f"[ID: {callId}] Hovor bol ukonceny: {origin} -> {destination}")
            elif rx_cancel.search(request_uri):
                self.processNonInvite()
            elif rx_options.search(request_uri):
                self.processNonInvite()
            elif rx_info.search(request_uri):
                self.processNonInvite()
            elif rx_message.search(request_uri):
                self.processNonInvite()
            elif rx_refer.search(request_uri):
                self.processNonInvite()
            elif rx_prack.search(request_uri):
                self.processNonInvite()
            elif rx_update.search(request_uri):
                self.processNonInvite()
            elif rx_subscribe.search(request_uri):
                self.sendResponse("200 0K / V poriadku")
            elif rx_publish.search(request_uri):
                self.sendResponse("200 0K / V poriadku")
            elif rx_notify.search(request_uri):
                self.sendResponse("200 0K / V poriadku")
            elif rx_code.search(request_uri):
                self.processCode()
            else:
                logging.error("request_uri %s" % request_uri)          
                #print "message %s unknown" % self.data
    
    def handle(self):
        data = self.request[0]
        if data[0] == 0x00:
            return
        data = data.decode("utf-8", errors="ignore")
        self.data = data.split("\r\n")
        self.socket = self.request[1]
        request_uri = self.data[0]
        if rx_request_uri.search(request_uri) or rx_code.search(request_uri):
            self.processRequest()
        else:
            if len(data) > 4:
                logging.warning("---\n>> server received [%d]:" % len(data))
                hexdump(data,' ',16)
                logging.warning("---")


    