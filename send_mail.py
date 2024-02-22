import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import os

def send_email(subject, to_email, header, content):
    # Email configuration
    sender_email = 'FollowUp2400@gmail.com' 
    sender_password = 'xnmi meau gbql flyj'  

    # Create the MIME object
    message = MIMEMultipart('related')
    message['From'] = sender_email
    message['To'] = to_email
    message['Subject'] = subject

    # Attach the HTML body with inline image
    body_with_inline_image = f"""\
    <html>
      <body>
        <img src="cid:image" alt="Embedded Image" style="width: 100%">
        <h1>{header}</h1>
        <p>{content}</p>
        
      </body>
    </html>
    """
    body_html = MIMEText(body_with_inline_image, 'html')
    message.attach(body_html)

    # Attach the image inline
    with open("logo2.png", 'rb') as image_file:
        image = MIMEImage(image_file.read(), name=os.path.basename("logo2.png"))
        image.add_header('Content-ID', '<image>')
        message.attach(image)

    # Connect to the SMTP server (in this case, Gmail's SMTP server)
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        # Start the TLS connection
        server.starttls()

        # Login to the Gmail account
        server.login(sender_email, sender_password)

        # Send the email
        server.sendmail(sender_email, to_email, message.as_string())
