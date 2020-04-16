from __future__ import print_function
import logging
from time import sleep
import boto3
import base64
from crhelper import CfnResource

logger = logging.getLogger(__name__)
helper = CfnResource(json_logging=True, log_level='DEBUG', boto_level='CRITICAL', polling_interval=3)

try:
    ssm_client = boto3.client('ssm')
    ec2_client = boto3.client('ec2')
except Exception as e:
    helper.init_failure(e)

def associate_profile(instance_id: str, instance_profile: str):
    logger.debug("Creating Association")
    associate_response = ec2_client.associate_iam_instance_profile(IamInstanceProfile={'Name': instance_profile},InstanceId=instance_id)
    response = ec2_client.describe_iam_instance_profile_associations(Filters=[{'Name': 'instance-id','Values': [instance_id]},{'Name': 'state','Values': ['associated']}])
    logger.debug("Waiting for Association")
    while len(response['IamInstanceProfileAssociations'])==0:
        sleep(15)
        response = ec2_client.describe_iam_instance_profile_associations(Filters=[{'Name': 'instance-id','Values': [instance_id]},{'Name': 'state','Values': ['associated']}])
    logger.debug("Association Complete")
    return
    
def get_command_output(instance_id, command_id):
    response = ssm_client.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
    if response['Status'] in ['Pending', 'InProgress', 'Delayed']:
        return
    return response


def send_command(instance_id, commands: [str]):
    logger.debug("Sending command to %s : %s" % (instance_id, commands))
    try:
        return ssm_client.send_command(
            InstanceIds=[instance_id], 
            DocumentName='AWS-RunShellScript', 
            Parameters={'commands': commands},
            CloudWatchOutputConfig={
                'CloudWatchLogGroupName': 'ssm-output-{}'.format(instance_id),
                'CloudWatchOutputEnabled': True
    }
        )
    except ssm_client.exceptions.InvalidInstanceId:
        logger.debug("Failed to execute SSM command", exc_info=True)
        return

def rezise_ebs(instance_id: str, volume_size: int):
    instance = ec2_client.describe_instances(Filters=[{'Name': 'instance-id', 'Values': [instance_id]}])['Reservations'][0]['Instances'][0]
    block_volume_id = instance['BlockDeviceMappings'][0]['Ebs']['VolumeId']
    ec2_client.modify_volume(VolumeId=block_volume_id,Size=volume_size)
    return

@helper.create
def create(event, context):
    logger.debug("Got Create")
    environment_id = event["ResourceProperties"]["EnvironmentId"]
    commands = ['sudo growpart /dev/xvda 1 ||sudo resize2fs /dev/xvda1|| sudo resize2fs /dev/nvme0n1p1'] + base64.b64decode(event["ResourceProperties"]["Commands"]).decode("utf-8").split('\n')
    size = event['ResourceProperties']['VolumeSize']
    response = ec2_client.describe_instances(Filters=[{'Name':'tag:aws:cloud9:environment', 'Values': [environment_id]}])
    logger.debug("response: {}".format(response))
    instance_id = response['Reservations'][0]['Instances'][0]['InstanceId']
    helper.Data["InstanceId"] = instance_id
    try:
        associate_profile(instance_id=instance_id, instance_profile=event['ResourceProperties']['InstanceProfile'])
    except Exception as e:
        raise Exception("Failed to set Associations", e)
    try:
        rezise_ebs(instance_id, int(size))
    except Exception as e:
        raise Exception("Failed to resize EBS", e)
    while True:
        send_response = send_command(instance_id, commands)
        if send_response:
            helper.Data["CommandId"] = send_response['Command']['CommandId']
            logger.debug("response: {}".format(send_response))
            
            break
        if context.get_remaining_time_in_millis() < 20000:
            raise Exception("Timed out attempting to send command to SSM")
        sleep(30)


@helper.poll_create
def poll_create(event, context):
    logger.info("Got create poll")
    try:
        cmd_output_response = get_command_output(helper.Data["InstanceId"], helper.Data["CommandId"])
    except ssm_client.exceptions.InvocationDoesNotExist:
        logger.debug('Invocation not available in SSM yet', exc_info=True)
    if cmd_output_response:
        if cmd_output_response['StandardErrorContent']:
            raise Exception("ssm command failed: " + cmd_output_response['StandardErrorContent'][:235])
        else:
            return helper.Data["InstanceId"]
    return


@helper.update
@helper.delete
def no_op(_, __):
    return
def handler(event, context):
    helper(event, context)