#!/usr/bin/python
import os
import cv2
import numpy as np
from datetime import datetime
from time import gmtime, strftime, time
from config import username, password, url, threshold, bucket_name, awsAccessKey, awsSecretKey, email
import logging
import boto3
from botocore.exceptions import ClientError
import os
import json
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

COOLDOWN = 10
initialTime = datetime.now()

def sendEmailWithImage(imageFileLocation, currentTime):
    # Replace sender@example.com with your "From" address.
    # This address must be verified with Amazon SES.
    SENDER = email

    # Replace recipient@example.com with a "To" address. If your account 
    # is still in the sandbox, this address must be verified.
    RECIPIENT = email

    # Specify a configuration set. If you do not want to use a configuration
    # set, comment the following variable, and the 
    # ConfigurationSetName=CONFIGURATION_SET argument below.
    # CONFIGURATION_SET = "ConfigSet"

    # If necessary, replace us-west-2 with the AWS Region you're using for Amazon SES.
    AWS_REGION = "us-east-1"

    # The subject line for the email.
    SUBJECT = "Motion Detected at "+currentTime

    # The full path to the file that will be attached to the email.
    ATTACHMENT = imageFileLocation

    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = "Hello,\r\nMotion was detected. You can check the image to see who it was."

    # The HTML body of the email.
    BODY_HTML = """\
    <html>
    <head></head>
    <body>
    <h1>Hello!</h1>
    <p>Motion was detected. You can check the image to see who it was.</p>
    </body>
    </html>
    """

    # The character encoding for the email.
    CHARSET = "utf-8"

    # Create a new SES resource and specify a region.
    client = boto3.client('ses',region_name=AWS_REGION, aws_access_key_id=awsAccessKey, aws_secret_access_key=awsSecretKey)

    # Create a multipart/mixed parent container.
    msg = MIMEMultipart('mixed')
    # Add subject, from and to lines.
    msg['Subject'] = SUBJECT 
    msg['From'] = SENDER 
    msg['To'] = RECIPIENT

    # Create a multipart/alternative child container.
    msg_body = MIMEMultipart('alternative')

    # Encode the text and HTML content and set the character encoding. This step is
    # necessary if you're sending a message with characters outside the ASCII range.
    textpart = MIMEText(BODY_TEXT.encode(CHARSET), 'plain', CHARSET)
    htmlpart = MIMEText(BODY_HTML.encode(CHARSET), 'html', CHARSET)

    # Add the text and HTML parts to the child container.
    msg_body.attach(textpart)
    msg_body.attach(htmlpart)

    # Define the attachment part and encode it using MIMEApplication.
    att = MIMEApplication(open(ATTACHMENT, 'rb').read())

    # Add a header to tell the email client to treat this part as an attachment,
    # and to give the attachment a name.
    att.add_header('Content-Disposition','attachment',filename=os.path.basename(ATTACHMENT))

    # Attach the multipart/alternative child container to the multipart/mixed
    # parent container.
    msg.attach(msg_body)

    # Add the attachment to the parent container.
    msg.attach(att)
    #print(msg)
    try:
        #Provide the contents of the email.
        response = client.send_raw_email(
            Source=SENDER,
            Destinations=[
                RECIPIENT
            ],
            RawMessage={
                'Data':msg.as_string(),
            },
        )
    # Display an error if something goes wrong.	
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])

def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    # Upload the file
    s3_client = boto3.client('s3', aws_access_key_id=awsAccessKey, aws_secret_access_key=awsSecretKey)
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


def diffImg(t0, t1, t2):
    d1 = cv2.absdiff(t2, t1)
    d2 = cv2.absdiff(t1, t0)
    return cv2.bitwise_and(d1, d2)

def handleChange(frame):
    global initialTime
    
    current_time = datetime.now()
    timePassed = current_time - initialTime
    if timePassed.total_seconds() >= COOLDOWN:
        formatted_time = current_time.strftime('%Y%m%d%H%M%S')
        fname = "./images/img%s.jpg"  % formatted_time
    
        if cv2.imwrite(fname, frame):
            print('Success')
            initialTime = current_time
        else:
            raise Exception("Could not create image.")
        upload_file(fname, bucket_name)
        sendEmailWithImage(fname, formatted_time)

    else:
        print("Image creation on cooldown, "+str(timePassed)+ " seconds left")

    


if __name__ == '__main__':
    rtsp_url = "rtsp://%s:%s@%s" % (username, password, url)

    print ("motion detector in: %s" % rtsp_url)
    cap=cv2.VideoCapture(rtsp_url)

    # Read three images first:
    img_minus = cap.read()[1]
    img = cap.read()[1]
    img_plus = cap.read()[1]

    t_minus = cv2.cvtColor(img_minus, cv2.COLOR_RGB2GRAY)
    t = cv2.cvtColor(np.copy(img), cv2.COLOR_RGB2GRAY)
    t_plus = cv2.cvtColor(img_plus, cv2.COLOR_RGB2GRAY)


    while(True):
        dif = diffImg(t_minus, t, t_plus)
        difSum = dif.sum()
        print(difSum)
        if difSum > threshold:
            handleChange(img)
    
        # Read next image
        img = cap.read()[1]
        t_minus = t
        t = t_plus
        t_plus = cv2.cvtColor(np.copy(img), cv2.COLOR_RGB2GRAY)

    cap.release()   