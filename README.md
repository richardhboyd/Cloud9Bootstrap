# Cloud9 IDE UserData
## Build The App

````bash
REGION=us-west-2
S3_BUCKET_NAME=$(aws sts get-caller-identity --query "Account" --output text)-${REGION}-$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 16 | head -n 1)
aws s3 mb s3://${S3_BUCKET_NAME} --region $REGION
# TODO Update Bucket Policy for SAR Access
sam build
sam package -t .aws-sam/build/template.yaml --s3-bucket $S3_BUCKET_NAME --output-template-file packaged.yaml
sam publish -t packaged.yaml --region $REGION
````
Now we'll fetch the ARN of the SAR App
````bash
aws serverlessrepo list-applications --query "Applications[?Name == 'Cloud9BootStrapper'].ApplicationId" --region $REGION --output text
````

## Usage
````yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  MyCloud9Env:
    Type: AWS::Cloud9::EnvironmentEC2
    Properties: 
      InstanceType: t2.micro

  BootStrapper:
    Type: AWS::Serverless::Application
    Properties:
      Location:
        ApplicationId: [SAR ARN]
        SemanticVersion: 0.1.0
      Parameters:
        Cloud9Environment: !Ref MyCloud9Env
        EBSVolumeSize: 75
        UserData: !Base64 |
          mkdir /home/ec2-user/environment/RichardWasHere
          touch /home/ec2-user/environment/RichardWasHere/README.md
          echo "Here is some text" >> /home/ec2-user/environment/RichardWasHere/README.md
````