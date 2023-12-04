# views.py
from django.shortcuts import render, redirect
from django.core.files.storage import default_storage
from .models import Video
import subprocess
import webvtt
import boto3
from boto3.dynamodb.conditions import Key
import json
from celery import shared_task
import subprocess


AWS_ACCESS_KEY_ID = ''
AWS_SECRET_ACCESS_KEY = ''
AWS_REGION = ''
AWS_STORAGE_BUCKET_NAME = ''

pre_signed_vtt_url = ""
video_name_sub = ""
def home(request):
        return render(request, 'index.html')



def UploadVid(request):
    if request.method == 'POST':
        video = request.FILES['video']

    # Create and write into a temperary file after chunking
        with open('temp_file.mp4', 'wb') as temp_file:
            for chunk in video.chunks():
                temp_file.write(chunk)

        video_name = video.name

    # Removing file extension "mp4"
        video_name_sub = video_name.split('.')[0]
        print('Chunks Created')

    # Extracting SRT subtitles from video chunks
        # function without celery class object
        # @shared_task
        # def run_ccextractor(video_file, video_name_sub):
        #     subprocess.run(['CCExtractor_win_portable\ccextractorwinfull.exe', video_file, '-o', f'subtitles/{video_name_sub}.srt'])
        # run_ccextractor.delay('temp_file.mp4', video_name_sub)

        subprocess.run(['CCExtractor_win_portable\ccextractorwinfull.exe',
                        'temp_file.mp4', '-o', 'subtitles/'+video_name_sub+'.srt'])  
        
        print('Subtitles Created')
        
    # Converting SRT to VTT
        input_path = 'subtitles/'+video_name_sub+'.srt'
        output_path = 'subtitles/'+video_name_sub+'.vtt'
        captions = webvtt.from_srt(input_path)
        captions.save(output_path) 


    # Uploading

    # Subtitle Vtt => JASON and Uploading it to Dynomodb
        result = subprocess.run(['webvtt-to-json', 'subtitles/'+video_name_sub+'.vtt', '-o', 'subtitles/'+video_name_sub+'.json'], capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr)
        SubtitleJson_to_Dynomo(video_name_sub)
        
    # Uploading Video to S3 
        s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                                 region_name=AWS_REGION,)
        print ("Client Created")

        default_storage.save(video_name, video)
        print("Saved to S3")

    # Get the Presigned URL
        pre_signed_url_video = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': AWS_STORAGE_BUCKET_NAME,
                'Key': video_name
            },
            ExpiresIn=3600)  

        print('Video url created : ', pre_signed_url_video)

    

    # Uploadin VTT Subtitle to S3 
        file_name = video_name_sub+'.vtt'
        with open('subtitles/'+video_name_sub+'.vtt', 'rb') as vtt_file:
            default_storage.save(file_name, vtt_file)  

        print('Subtitle Uploaded')

        pre_signed_vtt_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': AWS_STORAGE_BUCKET_NAME,
                'Key': file_name
            },
            ExpiresIn=3600)
        
        print('Subtitle Link Created : ', pre_signed_vtt_url)
        return render(request, 'index.html', {'video_file': pre_signed_url_video, 'sub': pre_signed_vtt_url})


vtt_file_path = pre_signed_vtt_url
  

def SubtitleJson_to_Dynomo(video_name_sub):

    # Creating session    
        session = boto3.Session(
            # aws_access_key_id=access_key,
            # aws_secret_access_key=secret_access_key,
            access_key = "",
            secret_access_key = "",
            region_name=''
        )

        video_name = video_name_sub
        dynamodb = session.resource('dynamodb')
        table = dynamodb.Table('vid_sub')
    # Load json
        with open('subtitles/'+video_name_sub+'.json', 'r') as json_file:
            subtitles = json.load(json_file)
    # Uploading to DynomoDB
        count = 0
        for subtitle in subtitles:
            start = subtitle['start']
            end = subtitle['end']
            lines = subtitle['lines']

            lines_string = '\n'.join(lines)

            count += 1
            try:
                response = table.put_item(
                    Item={
                        'video_name': video_name,
                        'start': start,
                        'end': end,
                        'lines': lines_string
                    }
                )
                print('Written File', count)
            except Exception as e:
                print('Error adding item:', str(e))
        print('Uploaded to DynamoDB:',response)
        
    
def View_KeyWord_Search(request):
    # Initialize Variable    
        result = []
        response = []

        if request.method == 'POST':
            search_word = request.POST.get('search')
            print('Word ',search_word)

            TABLE_NAME = "vid_sub"

    # Creating the DynamoDB Table Resource
            dynamodb = boto3.resource('dynamodb', 
                                    region_name="eu-north-1", 
                                    aws_access_key_id=AWS_ACCESS_KEY_ID, 
                                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
            
            table = dynamodb.Table(TABLE_NAME)
    # Query to DB
            response = table.query(
                KeyConditionExpression=Key('video_name').eq(video_name_sub) & Key('line').begins_with(search_word),
                ProjectionExpression='end,start,line'  
            )
            result=response['Items']
            print(response['Items'])
            
            print('Result Data ',response)
        return render(request, 'index.html', {'results': result})
