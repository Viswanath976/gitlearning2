import boto3
import pandas as pd
import requests
import json
import os
import uuid
from datetime import datetime
from io import StringIO

S3 = boto3.client('s3')
BUCKET = os.environ['S3_BUCKET']

def get_secret(name):
    client = boto3.client(
        'secretsmanager',
        region_name=os.environ.get(
            'AWS_REGION_NAME',
            'us-west-2'))
    r = client.get_secret_value(
        SecretId=name)
    return json.loads(
        r['SecretString'])

def get_blacklist_key():
    secret = get_secret(
        os.environ['BLACKLIST_SECRET'])
    return secret['value']

def check_blacklist_bulk(leads):
    """
    Send leads to Blacklist Alliance
    Returns only VALID records!
    """
    api_key = get_blacklist_key()
    url = "https://api.blacklistalliance.net/bulk"
    
    # Build payload
    # Email + Phone per lead
    payload = []
    for lead in leads:
        entry = {}
        if lead.get('email'):
            entry['email'] = \
                lead['email']
        if lead.get('phone'):
            entry['phone'] = \
                lead['phone']
        if entry:
            payload.append(entry)
    
    headers = {
        'x-api-key': api_key,
        'Content-Type':
            'application/json'
    }
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60
        )
        print(f"Blacklist status: "
              f"{response.status_code}")
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: "
                  f"{response.text}")
            return []
    except Exception as e:
        print(f"Blacklist error: {e}")
        return []

def lambda_handler(event, context):
    # Get input file from event
    input_key = event.get('input_key')
    run_id = event.get('run_id',
        f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}")

    # Auto detect latest
    # stage1 file if not provided
    if not input_key:
        response = S3.list_objects_v2(
            Bucket=BUCKET,
            Prefix='stage1_hygiene/')
        files = sorted(
            response.get(
                'Contents', []),
            key=lambda x: x['LastModified'],
            reverse=True)
        if not files:
            return {'error':
                'No stage1 files found!'}
        input_key = files[0]['Key']

    print(f"Input: {input_key}")
    print(f"Run ID: {run_id}")

    # Read CSV from S3
    obj = S3.get_object(
        Bucket=BUCKET,
        Key=input_key)
    df = pd.read_csv(StringIO(
        obj['Body'].read()
        .decode('utf-8')))
    print(f"Total rows: {len(df)}")

    # Filter PASSED leads only!
    passed_df = df[
        df['HYGIENE_STATUS'] == 'PASSED'
    ].copy()
    print(f"Passed leads: "
          f"{len(passed_df)}")

    if len(passed_df) == 0:
        return {
            'error': 'No passed leads!',
            'total': len(df),
            'passed': 0
        }

    # Prepare leads for API
    leads = passed_df.to_dict(
        orient='records')

    # Call Blacklist Alliance!
    # Returns ONLY valid leads!
    print("Calling Blacklist Alliance...")
    valid_leads = check_blacklist_bulk(
        leads)

    print(f"Valid leads returned: "
          f"{len(valid_leads)}")

    # Save valid leads to S3
    if valid_leads:
        valid_df = pd.DataFrame(
            valid_leads)
        valid_df['RUN_ID'] = run_id
        valid_df['BLACKLIST_CHECKED_AT'] = \
            datetime.now().isoformat()

        out_key = (
            f"stage2_blacklist/"
            f"mortgage_blacklist_"
            f"{run_id}.csv")

        buf = StringIO()
        valid_df.to_csv(
            buf, index=False)
        S3.put_object(
            Bucket=BUCKET,
            Key=out_key,
            Body=buf.getvalue())

        print(f"Saved to: {out_key}")
    else:
        out_key = None
        print("No valid leads!")

    summary = {
        'run_id': run_id,
        'input_file': input_key,
        'total_passed': len(passed_df),
        'valid_after_blacklist':
            len(valid_leads),
        'output_file': out_key
    }

    print(f"Done! "
          f"{json.dumps(summary)}")
    return summary
