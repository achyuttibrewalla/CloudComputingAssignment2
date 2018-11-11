from __future__ import print_function
import json
import boto3
import argparse
import json
import pprint
from botocore.vendored import requests
import sys
import urllib
from datetime import datetime
from botocore.exceptions import ClientError


# This client code can run on Python 2.x or 3.x.  Your imports can be
# simpler if you only need one of those.
try:
    # For Python 3.0 and later
    from urllib.error import HTTPError
    from urllib.parse import quote
    from urllib.parse import urlencode
except ImportError:
    # Fall back to Python 2's urllib2 and urllib
    from urllib2 import HTTPError
    from urllib import quote
    from urllib import urlencode


# Yelp Fusion no longer uses OAuth as of December 7, 2017.
# You no longer need to provide Client ID to fetch Data
# It now uses private keys to authenticate requests (API Key)
# You can find it on
# https://www.yelp.com/developers/v3/manage_app
API_KEY= "PIcMre748CZfPl1aXuW-G5YoyWSTt_Vjzt5Pqaq7P6L9moLhnE37rPOPoAp9O4Q1VFdbxCVEhXm6XQ86pr2bdP72M0jaSDO6iw9O-1yIPRqkcvSWDwQfp-hwr5vfW3Yx" 


# API constants, you shouldn't have to change these.
API_HOST = 'https://api.yelp.com'
SEARCH_PATH = '/v3/businesses/search'
BUSINESS_PATH = '/v3/businesses/'  # Business ID will come after slash.


# Defaults for our simple example.
SEARCH_LIMIT = 5



def request(host, path, api_key, url_params=None):
    """Given your API_KEY, send a GET request to the API.

    Args:
        host (str): The domain host of the API.
        path (str): The path of the API after the domain.
        API_KEY (str): Your API Key.
        url_params (dict): An optional set of query parameters in the request.

    Returns:
        dict: The JSON response from the request.

    Raises:
        HTTPError: An error occurs from the HTTP request.
    """
    #print(url_params)
    url_params = url_params or {}
    url = '{0}{1}'.format(host, quote(path.encode('utf8')))
    headers = {
        'Authorization': 'Bearer %s' % api_key,
    }

    #print(u'Querying {0} ...'.format(url))

    response = requests.request('GET', url, headers=headers, params=url_params)

    return response.json()


def search(api_key, term, location,openat):
    """Query the Search API by a search term and location.

    Args:
        term (str): The search term passed to the API.
        location (str): The search location passed to the API.

    Returns:
        dict: The JSON response from the request.
    """

    url_params = {
        'term': term.replace(' ', '+'),
        'location': location.replace(' ', '+'),
        'limit': SEARCH_LIMIT,
        'openAt' : openat
    }
    return request(API_HOST, SEARCH_PATH, api_key, url_params=url_params)





def query_api(term, location,openAt):
    """Queries the API by the input values from the user.

    Args:
        term (str): The search term to query.
        location (str): The location of the business to query.
    """
    return search(API_KEY, term, location, openAt)


    


def main():
    sqs = boto3.resource('sqs')
    sqsqueue = sqs.get_queue_by_name(QueueName = 'SuggestionRequests')
    i = 0
    allmessages = []
    messages = sqsqueue.receive_messages(MaxNumberOfMessages = 10)
    for message in sqsqueue.receive_messages(MaxNumberOfMessages=5):
         print('Message: {}'.format(message.body))
    #print("Length:", len(messages))
    #flag = True
    #while flag:
    for message in messages:
        API_data = json.loads(message.body)
        cuisine = API_data["Cuisine"]
        location = API_data["Location"]
        date = API_data["Date"]
        time = API_data["Time"]
        usr_email = API_data["email"]
        openAt = datetime.strptime(date + " " + time, '%Y-%m-%d %H:%M')
        #print("time1:", time)
        date = datetime.strptime(date,'%Y-%d-%m')
        #print("date2:", date)
        date = datetime.strftime(date, '%d %B %Y')
        #print("date3:", date)
        time = datetime.strptime(time, '%H:%M')
        time = datetime.strftime(time,'%I:%M %p')
        num_ppl = API_data["num_ppl"]
        usr_phone = API_data["phone_number"]
        #print("time:", time)
        url_params = {
        'term': cuisine,
        'location': location,
        'limit': SEARCH_LIMIT,
        'openAt' : openAt
        }
        
        try:
            yelp_reply = request(API_HOST, SEARCH_PATH, API_KEY, url_params)
        except HTTPError as error:
            sys.exit(
                'Encountered HTTP error {0} on {1}:\n {2}\nAbort program.'.format(
                    error.code,
                    error.url,
                    error.read(),
                )
            )
        
        email_text = "<p>Hello! Here are my {} restaurant suggestions for {} people, for {} at {} in {}:</p><ol>".format(cuisine, num_ppl, date, time, location)
        mobile_text = "Hello! Here are my {} restaurant suggestions for {} people, for {} at {} in {}:\n\n".format(cuisine, num_ppl, date, time, location)
        index = 1
        for i in range(len(yelp_reply["businesses"])):
            text = yelp_reply["businesses"][i]["name"]
            _loc = yelp_reply["businesses"][i]["location"]
            phone = yelp_reply["businesses"][i]["display_phone"]
            loc = "{}, {} ".format(_loc["display_address"][0],_loc["display_address"][1])
            email_text += "<li>{}:<ul><li>Address: {}</li><li>Phone Number: {}</li><br /></ul></li>".format(text,loc,phone)
            mobile_text += "{}.{}, \nAddress: {}, Phone Number: {}\n\n".format(index,text,loc,phone)
            index += 1
        
        
        snsClient = boto3.client('sns')
        snsClient.publish(
          PhoneNumber = str(usr_phone),
          Message = mobile_text
          )
        email_text + "</ol>"
        #print(str(usr_phone)) 
        ##Dynamo DB    
        dynamoResource = boto3.resource('dynamodb')
        dynamoTable = dynamoResource.Table('Restuarant_API')
        dynamoTable.put_item(
            Item={
            'primary_key' : message.message_id   ,
            'username': usr_email,
            'query': message.body,
            'results' : email_text
            }
        )
        
        
        # This address must be verified with Amazon SES.
        SENDER = "Dining Concierge <aj2419@nyu.edu>"
        
        # is still in the sandbox, this address must be verified.
        RECIPIENT = str(usr_email)    
        #"aj2419@nyu.edu"
        
        #CONFIGURATION_SET = "ConfigSet"
        AWS_REGION = "us-east-1"
        
        # The subject line for the email.
        SUBJECT = "Restaurants"
        
        # The email body for recipients with non-HTML email clients.
        BODY_TEXT = (email_text)
                    
        # The HTML body of the email.
        BODY_HTML = """<html><head></head><body> 
                     <h1>Restaurants</h1> 
                     """ 
                     
        BODY_HTML2= """ 
                     </body>
                     </html>
                    """            
        #Text for the email
        text_email = BODY_HTML + email_text + BODY_HTML2
        
        # The character encoding for the email.
        CHARSET = "UTF-8"
        
        # Create a new SES resource and specify a region.
        client = boto3.client('ses',region_name=AWS_REGION)
        
        # Try to send the email.
        try:
            #Provide the contents of the email.
            response = client.send_email(
                Destination={
                    'ToAddresses': [
                        RECIPIENT,
                    ],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': CHARSET,
                            'Data': text_email,
                        },
                        'Text': {
                            'Charset': CHARSET,
                            'Data': BODY_TEXT,
                        },
                    },
                    'Subject': {
                        'Charset': CHARSET,
                        'Data': SUBJECT,
                    },
                },
                Source=SENDER,
                # If you are not using a configuration set, comment or delete the
                # following line
                #ConfigurationSetName=CONFIGURATION_SET,
            )
        # Display an error if something goes wrong. 
        except ClientError as e:
            print(e.response['Error']['Message'])
        else:
            
            print("Email sent! Message ID:"),
            #print(response['MessageId'])
            print(RECIPIENT)
        message.delete()
        
        
        

def lambda_handler(event, context):
    main()
    # TODO implement
   