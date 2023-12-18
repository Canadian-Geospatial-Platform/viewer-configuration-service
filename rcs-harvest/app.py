import os
import io
import json
import boto3
import requests
import logging

from lambda_multiprocessing import Pool
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import boto3

RCS_CONFIG_PATH = os.environ['RCS_CONFIG_PATH']
GCS_TABLE       = os.environ['GCS_TABLE']
GEOCORE_ID_API  = os.environ['GEOCORE_ID_API']

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    
    rcs_configuration_path = RCS_CONFIG_PATH
    viewer_configuration_table = GCS_TABLE
    geocore_api_path = GEOCORE_ID_API

    id = None
    lang = None
    message = ""
    rcs_response = ""
    gcs_response = ""
    metadata_response = ""
    
    try:
        id = str(event["queryStringParameters"]["id"])
    except:
        message += "id was not supplied or is invalid"

    try:
        lang = str(event["queryStringParameters"]["lang"])
    except:
        message += ", lang was not supplied or is invalid"
    
    try:
        key = str(event["queryStringParameters"]["key"])
    except:
        key = False

    try:
        if (str(event["queryStringParameters"]["metadata"]).upper() == 'TRUE'):
            metadata = True
        else:
            metadata = False
    except:
        metadata = False

    if not id or not lang:
        response = {"message": message}
        return response
    
    required = [False, False, metadata]
    keys = ["gcs", "rcs", "metadata"]
    message_obj = []
    response_obj = []
    reponse = []
    message_list = {}
    configuration = [viewer_configuration_table, rcs_configuration_path, geocore_api_path]
    
    
    iterable_pool_data = [(id ,lang, False, viewer_configuration_table, 'gcs'), 
                          (id, lang, False, rcs_configuration_path, 'rcs'),
                          (id, lang, metadata, geocore_api_path, 'metadata')]
    
    with Pool() as p:
        response = p.starmap(get_generic, iterable_pool_data)
    
    for i in range(0, len(keys)):
        message_obj.append(json.loads(response[i][1]))
        response_obj.append(response[i][0])
    
    for item in message_obj:
        message_list.update(item)
        
    combined_dict = {key: value for key, value in zip(keys, response_obj)}
    
    """
    Generate API response
    """

    response = {
        "headers": {"Content-type": "application/json"},
        "statusCode": "200",
        "id": id,
        "message": message_list,
        "reponse": combined_dict
    }
    return response


def get_generic(id, lang, required, path, key):
    message = ""
    if key == "rcs":
        rcs_url_request = path + "/" + lang + "/" + id
        headers = {'Accept': 'application/json'}
        rcs_response = requests.get(rcs_url_request, headers=headers)
    
        if rcs_response.ok:
            response = json.loads(rcs_response.text)
            message += '{"rcs": "Success returning RCS"}'
        else:
            message += '{"rcs": "Could not access RCS: ' + rcs_url_request + '"}'
    elif key == "gcs":
        gcs_response = read_configuration_by_id(id, path, 'ca-central-1', dynamodb=None)
        first_element = gcs_response[0]
        json_string = first_element['plugins']
        json_data = json.loads(json_string)
        response = json_data[0]['RAMPS']
    
        if response != None:
            message += '{"gcs": "Success returning GCS"}'
        else:
            message += '{"gcs": "Could not access GCS: ' + id + '}"'
    elif key == "metadata":
        if required == True:
            metadata_url_request = path + "?lang=" + lang + "&id=" + id
            headers = {'Accept': 'application/json'}
            metadata_response = requests.get(metadata_url_request, headers=headers)
            
            if metadata_response.ok:
                response = json.loads(metadata_response.text)['body']['Items']
                message += '{"metadata": "Success returning metadata"}'
            else:
                message += '{"metadata": "Could not access metadata: ' + metadata_url_request + '"}'
        else:
            response = ""
            message += '{"metadata": "metadata not requested"}'

    return response, message
    

def read_configuration_by_id(uuid, viewer_configuration_table, region, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=region)

    table = dynamodb.Table(viewer_configuration_table)
    try:
        response = table.query(
            KeyConditionExpression=Key('uuid').eq(uuid)
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Items']

# Wrapper to safely load json objects in case it is null
def nonesafe_loads(obj):
    if obj is not None:
        return json.loads(obj)
        

"""

def get_gcs(id, lang, required, viewer_configuration_table):
    message = ""
    gcs_response = read_configuration_by_id(id, viewer_configuration_table, 'ca-central-1', dynamodb=None)

    # Access the first element in the list
    first_element = gcs_response[0]
    # Convert the JSON string to a dictionary
    json_string = first_element['plugins']
    json_data = json.loads(json_string)
    # Now we can access the nested structure
    gcs_response = json_data[0]['RAMPS']

    if gcs_response != None:
        message += '{"gcs": "Success returning GCS"}'
    else:
        message += '{"gcs": "Could not access GCS: ' + id + '}"'
    
    return gcs_response, message

def get_rcs(id, lang, required, rcs_configuration_path):
    message = ""
    rcs_url_request = rcs_configuration_path + "/" + lang + "/" + id
    
    #Add headers to accept JSON
    headers = {'Accept': 'application/json'}
    #Use requests to get the RCS
    rcs_response = requests.get(rcs_url_request, headers=headers)

    if rcs_response.ok:
        rcs_response = json.loads(rcs_response.text)
        message += '{"rcs": "Success returning RCS"}'
    else:
        message += '{"rcs": "Could not access RCS: ' + rcs_url_request + '"}'

    return rcs_response, message
    
def get_metadata(id, lang, required, geocore_api_path):
    message = ""
    if required == True:
        metadata_url_request = geocore_api_path + "?lang=" + lang + "&id=" + id
        #Add headers to accept JSON
        headers = {'Accept': 'application/json'}
        #Use requests to get the geocore metadata
        metadata_response = requests.get(metadata_url_request, headers=headers)
        
        if metadata_response.ok:
            metadata_response = json.loads(metadata_response.text)['body']['Items']
            message += '{"metadata": "Success returning metadata"}'
        #else:
            #message += '{"metadata": "Could not access metadata: ' + metadata_url_request + '"}'
    else:
        metadata_response = ""
        message += '{"metadata": "metadata not requested"}'
    
    return metadata_response, message

    #Fetch the GCS configs
    try:
        gcs_response, gcs_message = get_gcs(id, lang, required, viewer_configuration_table)
        message = json.loads(gcs_message)
    except:
        message.update(json.loads('{"gcs": "gcs error"}'))
        
    
    #Fetch the RCS configs
    try:
        rcs_response, rcs_message = get_rcs(id, lang, required, rcs_configuration_path)
        rcs_message = json.loads(rcs_message)
        message.update(rcs_message)
    except:
        message.update(json.loads('{"rcs": "rcs error"}'))

    
    #Fetch geocore metadata
    try:
        metadata_response, metadata_message = get_metadata(id, lang, required, geocore_api_path)
        metadata_message = json.loads(metadata_message)
        message.update(metadata_message)
    except:
        message.update(json.loads('{"metadata": "metadata error"}'))

    """