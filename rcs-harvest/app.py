import os
import io
import json
import boto3
import requests
import logging

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

RCS_CONFIG_PATH = os.environ['RCS_CONFIG_PATH']
GCS_TABLE       = os.environ['GCS_TABLE']

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    
    rcs_configuration_path = RCS_CONFIG_PATH
    viewer_configuration_table = GCS_TABLE
    message = ""
    uuid = ""
    lang = ""
    
    rcs_response = ""
    gcs_response = ""
    response_data = ""
    
    try:
        uuid = str(event["queryStringParameters"]["uuid"])
    except:
        message = "UUID was not supplied or is invalid"

    try:
        lang = str(event["queryStringParameters"]["lang"])
    except:
        message = "lang was not supplied or is invalid"

    """
    Handle the GCS
    """
    
    gcs_response = read_configuration_by_uuid(uuid, viewer_configuration_table, 'ca-central-1', dynamodb=None)

    # Access the first element in the list
    first_element = gcs_response[0]
    # Convert the JSON string to a dictionary
    json_string = first_element['plugins']
    json_data = json.loads(json_string)
    # Now we can access the nested structure
    gcs_response = json_data[0]['RAMPS']

    if gcs_response != None:
        message += '{"gcs": "Success returning GCS"'
    else:
        message += '{"gcs": "Could not access GCS: ' + uuid + '"'
        
    """
    Handle the RCS
    """

    url_request = rcs_configuration_path + "/" + lang + "/" + uuid
    
    #Add headers to accept JSON
    headers = {'Accept': 'application/json'}
    #Use requests to get the RCS
    rcs_response = requests.get(url_request, headers=headers)

    if rcs_response.ok:
        rcs_response = json.loads(rcs_response.text)
        message += ', "rcs": "Success returning RCS"}'
    else:
        message += ', "rcs": "Could not access RCS: ' + url_request + '"}'
    
    response = {
        "uuid": uuid,
        "message": nonesafe_loads(message),
        "reponse": 
            {
                "rcs": rcs_response,
                "gcs": gcs_response
            }
    }
    return response

def read_configuration_by_uuid(uuid, viewer_configuration_table, region, dynamodb=None):
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
