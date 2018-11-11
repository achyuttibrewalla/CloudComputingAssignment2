import math
import dateutil.parser
import datetime
import time
import os
import logging
import re
import boto3
import json


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

""" --- Helpers to build responses which match the structure of the necessary dialog actions --- """

def get_slots(intent_request):
    return intent_request['currentIntent']['slots']


def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ElicitSlot',
            'intentName': intent_name,
            'slots': slots,
            'slotToElicit': slot_to_elicit,
            'message': message
        }
    }


def close(session_attributes, fulfillment_state, message):
    response = {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': message
        }
    }

    return response


def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }


""" --- Helper Functions --- """


def parse_int(n):
    try:
        return int(n)
    except ValueError:
        return float('nan')


def build_validation_result(is_valid, violated_slot, message_content):
    if message_content is None:
        return {
            "isValid": is_valid,
            "violatedSlot": violated_slot,
        }

    return {
        'isValid': is_valid,
        'violatedSlot': violated_slot,
        'message': {'contentType': 'PlainText', 'content': message_content}
    }


def isvalid_date(date):
    try:
        dateutil.parser.parse(date)
        return True
    except ValueError:
        return False

def isvalid_email(email):
    try:
        if len(email) > 7:
            if re.match("^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,4})$", email) != None:
                return True
        return False
    except ValueError:
        return False

def isvalid_number(phone_number):
    try:
        if len(phone_number)== 10:
            # if re.match("\w{3}-\w{3}-\w{4}", phone_number) != None:
            return True
        return False
    except ValueError:
        return False


def validate_dining_sugg(cuisine,date,time,location,num_ppl,email,phone_number):

    if num_ppl is not None and int(num_ppl) < 1:
            return build_validation_result(False,
                                            'People',
                                            'Can you please provide the correct number of people in your party?')

    valid_cuisines = ['japanese','thai','indian','chinese','american','french','mexican','italian','mediterranean','ethopian']

    if cuisine is not None and cuisine.lower() not in valid_cuisines:
        return build_validation_result(False,
                                       'Cuisine',
                                       'We do not have {}, would you like a different type of Cuisine. '
                                       ' Our most popular cuisine is Chinese'.format(cuisine))

    valid_locations = ['nyc','manhattan','brooklyn','new york', 'los angeles', 'chicago', 'houston', 'philadelphia', 'phoenix', 'san antonio',
                    'san diego', 'dallas', 'san jose', 'austin', 'jacksonville', 'san francisco', 'indianapolis',
                    'columbus', 'fort worth', 'charlotte', 'detroit', 'el paso', 'seattle', 'denver', 'washington dc',
                    'memphis', 'boston', 'nashville', 'baltimore', 'portland']

    if location is not None and location.lower() not in valid_locations:
        return build_validation_result(False,
                                      'Location',
                                      'We currently do not support {} as a valid destination.'
                                      ' Can you try a different city?'.format(location))
                                       
    if date is not None:
        if not isvalid_date(date):
            return build_validation_result(False, 'DineDate', 'I did not understand that, what date would you like to dine?')
        elif datetime.datetime.strptime(date, '%Y-%m-%d').date() < datetime.date.today():
            return build_validation_result(False, 'DineDate', 'Reservations must be scheduled in advance. Can you try a different date?')

    if time is not None:
        if len(time) != 5:
            # Not a valid time; use a prompt defined on the build-time model.
            return build_validation_result(False, 'DineTime', None)

        hour, minute = time.split(':')
        hour = parse_int(hour)
        minute = parse_int(minute)
        if math.isnan(hour) or math.isnan(minute):
            # Not a valid time; use a prompt defined on the build-time model.
            return build_validation_result(False, 'DineTime', None)

    if email is not None and not isvalid_email(email):
        return build_validation_result(False,'Email', 'Please enter a valid email address')

    if phone_number is not None and not isvalid_number(phone_number):
        return build_validation_result(False,'PhoneNumber', 'Please enter a valid US phone number without the country code')


    return build_validation_result(True, None, None)


""" --- Functions that control the bot's behavior --- """


def dining_sugg(intent_request):
    
    cuisine = get_slots(intent_request)["Cuisine"]
    email= get_slots(intent_request)["Email"]
    date = get_slots(intent_request)["DineDate"]
    time = get_slots(intent_request)["DineTime"]
    location= get_slots(intent_request)["Location"]
    num_ppl = get_slots(intent_request)["People"]
    phone_number = get_slots(intent_request)["PhoneNumber"]
    source = intent_request['invocationSource']

    if source == 'DialogCodeHook':
        # Perform basic validation on the supplied input slots.
        # Use the elicitSlot dialog action to re-prompt for the first violation detected.
        slots = get_slots(intent_request)
        validation_result = validate_dining_sugg(cuisine,date,time,location,num_ppl,email,phone_number)
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            return elicit_slot(intent_request['sessionAttributes'],
                               intent_request['currentIntent']['name'],
                               slots,
                               validation_result['violatedSlot'],
                               validation_result['message'])

        
        output_session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
        
        return delegate(output_session_attributes, get_slots(intent_request))

    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName='SuggestionRequests')
    phone_number="+1"+phone_number
    data = json.dumps({
        'Location': location,
        'Date': date,
        'Time': time,
        'Cuisine': cuisine,
        'email': email,
        'num_ppl':num_ppl,
        'phone_number':phone_number,
    })

    response = queue.send_message(
        MessageBody=data,
        # MessageGroupId='messageGroup1'
    )

    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Thanks, I have send you your dining suggestions. Have a good day!'})


""" --- Intents --- """


def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """

    logger.debug('dispatch userId={}, intentName={}'.format(intent_request['userId'], intent_request['currentIntent']['name']))

    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'RestaurantSuggestion':
        return dining_sugg(intent_request)

    raise Exception('Intent with name ' + intent_name + ' not supported')


""" --- Main handler --- """


def lambda_handler(event, context):
    """
    Route the incoming request based on intent.
    The JSON body of the request is provided in the event slot.
    """
    # By default, treat the user request as coming from the America/New_York time zone.
    os.environ['TZ'] = 'America/New_York'
    time.tzset()
    logger.debug('event.bot.name={}'.format(event['bot']['name']))

    return dispatch(event)
