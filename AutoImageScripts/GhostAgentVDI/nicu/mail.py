"""This module contains class for sending emails."""

import smtplib
from email.MIMEText import MIMEText

__all__ = ['Mail']


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
