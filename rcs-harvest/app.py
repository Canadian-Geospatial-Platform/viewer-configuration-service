import os
import json
import boto3
import base64
import binascii
import requests
import logging
import datetime

from lambda_multiprocessing import Pool
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

RCS_CONFIG_PATH = os.environ['RCS_CONFIG_PATH']
GCS_TABLE       = os.environ['GCS_TABLE']
GEOCORE_ID_API  = os.environ['GEOCORE_ID_API']

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    return handle_request(event, context)

def handle_request(event, context):
    rcs_configuration_path = RCS_CONFIG_PATH
    viewer_configuration_table = GCS_TABLE
    geocore_api_path = GEOCORE_ID_API

    method = str(event["method"]).upper()
    if method == 'POST':
        return handle_post_request(event, viewer_configuration_table)
    elif method == 'GET':
        return handle_get_request(event, rcs_configuration_path, viewer_configuration_table, geocore_api_path)
    else:
        return {
            "headers": {"Content-type": "application/json"},
            "statusCode": 405,
            "body": json.dumps({"message": "Method Not Allowed"})
        }

def handle_post_request(event, viewer_configuration_table):
    message = ""
    
    try:
        # Check if the body is Base64 encoded
        if isinstance(event["body"], str):
            if is_base64_encoded(event["body"]):
                json_bytes = base64.b64decode(event["body"])
            else:
                json_bytes = event["body"].encode('utf-8')
            json_data = json.loads(json_bytes)
        elif isinstance(event["body"], dict):
            json_data = event["body"]
        else:
            raise ValueError("Invalid body format")
        
        #print("json_data: ", json_data)
        if isinstance(json_data, str):
            json_data = json.loads(json_data)  # Parsing if it's a string
        gcs_data = json_data["body"]["gcs"]  # Extracting 'gcs' from the body
        #print("gcs_data: ", gcs_data)
    except (KeyError, json.JSONDecodeError, ValueError):
        message += "json_data was not supplied or is invalid"
        return {
            "headers": {"Content-type": "application/json"},
            "statusCode": 400,
            "body": json.dumps({"message": message})
        }
    
    id = json_data["body"]["id"]
    print("gcs_data: ", id)
    if not id:
        message += "no id was supplied or is invalid"
    else:
        create_configuration_by_id(id, viewer_configuration_table, gcs_data, 'ca-central-1', dynamodb=None)
        message += f"Inserted supplied data for id: {id}"

    return {
        "headers": {"Content-type": "application/json"},
        "method": "POST",
        "statusCode": 201,
        "body": {
            "message": message,
        }
    }

def handle_get_request(event, rcs_configuration_path, viewer_configuration_table, geocore_api_path):
    message = ""
    try:
        id = str(event["id"])
    except KeyError:
        message += "id was not supplied or is invalid"

    try:
        lang = str(event["lang"])
    except KeyError:
        message += ", lang was not supplied or is invalid"
    
    try:
        if str(event["metadata"]).upper() == 'TRUE':
            metadata = True
        else:
            metadata = False
    except KeyError:
        metadata = False

    if not id or not lang:
        return {"message": message}
            
    id_list = id.split(',')
    
    required = [False, False, metadata]
    keys = ["gcs", "rcs", "metadata"]
    message_obj = []
    response_obj = []
    message_list = {}
    configuration = [viewer_configuration_table, rcs_configuration_path, geocore_api_path]
    
    iterable_pool_data = [(id_list, lang, True, viewer_configuration_table, 'gcs'), 
                          (id_list, lang, True, rcs_configuration_path, 'rcs'),
                          (id_list, lang, metadata, geocore_api_path, 'metadata')]
    
    with Pool() as p:
        response = p.starmap(get_generic, iterable_pool_data)
    
    for i in range(len(keys)):
        message_obj.append(json.loads(response[i][1]))
        response_obj.append(response[i][0])
    
    for item in message_obj:
        message_list.update(item)
        
    combined_dict = {key: value for key, value in zip(keys, response_obj)}
    
    return {
        "headers": {"Content-type": "application/json"},
        "statusCode": 200,
        "method": "GET",
        "id": id,
        "message": message_list,
        "response": combined_dict
    }

def get_generic(id_list, lang, required, path, key):
    message = ""
    response = {}
    if key == "rcs":
        # Note: RCS already supports the ability to return multiple ids from a single request
        lang_list = ['en', 'fr']
        for lang in lang_list:
            id = ",".join(id_list)
            rcs_url_request = f"{path}/{lang}/{id}"
            headers = {'Accept': 'application/json'}
            rcs_response = requests.get(rcs_url_request, headers=headers)

            if rcs_response.ok:
                response[lang] = json.loads(rcs_response.text)
                message = '{"rcs": "Success returning RCS"}' if response else '{"rcs": "RCS not found"}'
            else:
                message += f'{{"rcs": "Could not access RCS: {rcs_url_request}"}}'
    elif key == "gcs":
        # Note: GCS is obtained from a dynamodb table
        gcs_list = []
        try:
            for id in id_list:
                gcs_response = read_configuration_by_id(id, path, 'ca-central-1', dynamodb=None)
                if gcs_response['Items']:
                    json_data = json.loads(gcs_response['Items'][0]['plugins'])
                    gcs_list.append(json_data[0].get('RAMPS', json_data[0]))
                else:
                    response_string = f'{{"en": "{id} not found", "fr": "{id} pas trouvé"}}'
                    gcs_list.append(json.loads(response_string))
                    message = '{"gcs": "GCS not found"}'

            response = gcs_list if gcs_list else json.loads("[]")
            message = '{"gcs": "Success returning GCS"}' if gcs_list else '{"gcs": "GCS not found"}'
        except IndexError:
            response = json.loads("[]")
            message = '{"gcs": "No GCS entry found"}'
        except Exception:
            response = json.loads("[]")
            message = '{"gcs": "Error returning GCS"}'
    elif key == "metadata":
        metadata_list = []
        if required:
            for id in id_list:
                metadata_url_request = f"{path}?lang={lang}&id={id}"
                headers = {'Accept': 'application/json'}
                metadata_response = requests.get(metadata_url_request, headers=headers)

                if metadata_response.ok:
                    try:
                        temp = json.loads(metadata_response.text)['body']['Items']
                        metadata_list.append(temp)
                    except (KeyError, TypeError):
                        response = json.loads("[]")
                        message = '{"metadata": "Metadata not found"}'
                else:
                    response = json.loads("[]")
                    message = f'{{"metadata": "Could not access metadata: {metadata_url_request}"}}'

            response = metadata_list if metadata_list else json.loads("[]")
            message = '{"metadata": "Success returning metadata"}' if metadata_list else '{"metadata": "Metadata not found"}'
        else:
            response = json.loads("[]")
            message = '{"metadata": "Metadata not requested"}'

    return response, message

def read_configuration_by_id(uuid, viewer_configuration_table, region, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=region)

    table = dynamodb.Table(viewer_configuration_table)
    try:
        response = table.query(KeyConditionExpression=Key('uuid').eq(uuid))
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response

def create_configuration_by_id(uuid, viewer_configuration_table, json_data, region, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        
    dateTime = datetime.datetime.utcnow().isoformat()[:-7] + 'Z'
    
    json_string = json.dumps(json_data)
    
    table = dynamodb.Table(viewer_configuration_table)
    
    response = table.put_item(
       Item={
            'uuid': uuid,
            'plugins': json_string,
            'datetime': dateTime
        }
    )
    
    if response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 200:
        print("Item added successfully.")
    else:
        print(f"Error: {response}")

def is_base64_encoded(data):
    try:
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        elif isinstance(data, bytes):
            data_bytes = data
        else:
            return False
        
        return base64.b64encode(base64.b64decode(data_bytes)) == data_bytes
    except (binascii.Error, ValueError):
        return False

def nonesafe_loads(obj):
    if obj is not None:
        return json.loads(obj)
