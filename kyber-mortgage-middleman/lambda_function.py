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

def get_middleman_config():
    secret = get_secret(
        os.environ['MIDDLEMAN_SECRET'])
    return secret

def post_to_middleman(lead, config):
    """Post single lead to Middleman"""
    url = config.get('api_url','')
    api_key = config.get('api_key','')

    # Map fields to Middleman format
    payload = {
        "email": lead.get(
            'email',''),
        "firstName": lead.get(
            'first_name',''),
        "lastName": lead.get(
            'last_name',''),
        "phone": lead.get(
            'phone',''),
        "address": lead.get(
            'address',''),
        "city": lead.get(
            'city',''),
        "state": lead.get(
            'state',''),
        "zip": str(lead.get(
            'zip','')),
        "loanAmount": lead.get(
            'loan_amount',''),
        "loanType": lead.get(
            'loan_type',''),
        "propertyValue": lead.get(
            'mortgage_balance',''),
        "creditBand": lead.get(
            'credit_band',''),
        "trustedFormUrl": lead.get(
            'trusted_form_url',''),
        "isMilitary": lead.get(
            'is_military',''),
    }

    headers = {
        'Authorization':
            f'Bearer {api_key}',
        'Content-Type':
            'application/json'
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )
        return {
            'status_code':
                response.status_code,
            'response':
                response.json()
                if response.content
                else {}
        }
    except Exception as e:
        return {
            'status_code': 0,
            'response':
                {'error': str(e)}
        }

def lambda_handler(event, context):
    # Get input file
    input_key = event.get('input_key')
    run_id = event.get('run_id',
        f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}")

    # Auto detect latest stage2 file
    if not input_key:
        response = S3.list_objects_v2(
            Bucket=BUCKET,
            Prefix='stage2_blacklist/')
        files = sorted(
            response.get(
                'Contents', []),
            key=lambda x:
                x['LastModified'],
            reverse=True)
        if not files:
            return {'error':
                'No stage2 files!'}
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
    print(f"Total leads: {len(df)}")

    # Get Middleman config
    config = get_middleman_config()

    posted = []
    failed = []

    for idx, row in df.iterrows():
        email = row.get('email','')
        print(f"{idx+1}/{len(df)}: "
              f"Posting {email}")

        result = post_to_middleman(
            row.to_dict(), config)

        status = result['status_code']
        response = result['response']

        row_dict = row.to_dict()
        row_dict['MIDDLEMAN_STATUS'] = \
            'POSTED' if status in \
            (200,201) else 'FAILED'
        row_dict['MIDDLEMAN_RESPONSE'] \
            = json.dumps(response)
        row_dict['POSTED_AT'] = \
            datetime.now().isoformat()
        row_dict['RUN_ID'] = run_id

        if status in (200, 201):
            posted.append(row_dict)
            print(f"✅ Posted: {email}")
        else:
            failed.append(row_dict)
            print(f"❌ Failed: {email}"
                  f" - {status}")

    # Save posted CSV
    if posted:
        posted_df = pd.DataFrame(posted)
        posted_key = (
            f"stage3_posted/"
            f"mortgage_posted_"
            f"{run_id}.csv")
        buf = StringIO()
        posted_df.to_csv(
            buf, index=False)
        S3.put_object(
            Bucket=BUCKET,
            Key=posted_key,
            Body=buf.getvalue())
        print(f"Posted saved: "
              f"{posted_key}")
    else:
        posted_key = None

    # Save failed CSV
    if failed:
        failed_df = pd.DataFrame(failed)
        failed_key = (
            f"stage3_posted/"
            f"mortgage_failed_"
            f"{run_id}.csv")
        buf = StringIO()
        failed_df.to_csv(
            buf, index=False)
        S3.put_object(
            Bucket=BUCKET,
            Key=failed_key,
            Body=buf.getvalue())
        print(f"Failed saved: "
              f"{failed_key}")
    else:
        failed_key = None

    summary = {
        'run_id': run_id,
        'total': len(df),
        'posted': len(posted),
        'failed': len(failed),
        'posted_file': posted_key,
        'failed_file': failed_key
    }

    print(f"Done! "
          f"{json.dumps(summary)}")
    return summary
