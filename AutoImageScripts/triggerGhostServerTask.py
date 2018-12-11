#!/usr/bin/env python
"""
Python script to send a simple tcp message to rtimgserver to ghost the VST daily test
"""

import socket
import os
import re
import sys
import smtplib
from email.mime.text import MIMEText

serverName = '10.144.16.149'
serverPort = 5555
ghostTask = 'command-line-arg-not-present'

REMOTE_COMPILE_SERVER = ['STS_Test',
                         'fpga-qv-comp2']

reportRecipients = ["yang.liu3@ni.com",
                    "shuaishuaiweiba@126.com"]


def triggerGhostServer(ghostTask, serverName, serverPort):
    print ('Sending ghost command')
    print ('Server: ' + serverName)
    print ('Port: ' + str(serverPort))
    print ('Task: ' + ghostTask)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((serverName, serverPort))
        s.send(ghostTask)
        s.close()
    except Exception as error:
        print ('Error Encountered')
        print (error)


class Mail:
    """Send email using smtp"""
    def __init__(self, host, port, user, password=None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def send(self, to, subject, content='', subtype='plain', charset='utf-8',
             cc=None, bcc=None):
        # create a text/* type MIME document.
        msg = MIMEText(content, subtype, charset)
        msg['Subject'] = subject
        msg['From'] = self.user
        msg['To'] = ','.join(to)
        if cc:
            msg['Cc'] = ','.join(cc)
            to.extend(cc)
        if bcc:
            msg['Bcc'] = ','.join(bcc)
            to.extend(bcc)
        s = smtplib.SMTP(self.host, self.port)
        s.ehlo()
        if self.password:
            s.starttls()
            s.ehlo()
            s.login(self.user, self.password)
        s.sendmail(self.user, to, msg.as_string())
        s.quit()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        ghostTask = sys.argv[1]
    if len(sys.argv) > 2:
        serverName = sys.argv[2]

    ghostMachine = ghostTask.split('\\')[-1]

    if (ghostMachine not in REMOTE_COMPILE_SERVER):
        try:
            triggerGhostServer(ghostTask, serverName, serverPort)
        except Exception as e:
            print(e)
    else:
        '''
        mail = Mail('mailmass', 25, 'yang.liu3@ni.com')
        subject = 'Skip ghosting %s. Please remember to ghost it manually 5-6 hours later' % ghostTask
        content = 'FPGA\'s stack is at rating 1 (Either testing or ready for test soon).\n\n' \
                  'Please remember to ghost %s manually 5-6 hours later' % ghostTask
        mail.send(reportRecipients, subject, content)
        '''
        print("Gost failed")

