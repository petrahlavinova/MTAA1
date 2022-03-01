# Zadanie 1. SIP PROXY
# MTAA 2021/2022 Letný semester
# Petra Hlavinová

import socketserver
import lib
HOST = '0.0.0.0'
PORT = 5060

if __name__ == "__main__":  
    lib.prepare()  
    server = socketserver.UDPServer((HOST, PORT), lib.UDPHandler)
    server.serve_forever()