#!/opt/venv/bin/python
"""Docker CLI guard for the services agent. Not a replacement for host egress policy."""
import os
import sys

VALUE_FLAGS = {'-v','--volume','-e','--env','--env-file','--name','--network','--net','--user','-u',
               '--workdir','-w','--entrypoint','--gpus','--ipc','--shm-size','--label','-l','--hostname','-h',
               '--ulimit','--add-host','--device','--group-add','--security-opt','--cap-add','--cap-drop',
               '--mount','--cpus','--memory','-m','--pid','--pull','--publish','-p','--runtime'}
BOOL_FLAGS = {'--rm','-d','--detach','-i','--interactive','-t','--tty','-it','-dit','--init'}
READ_COMMANDS = {'version','--version','info','ps','images','inspect','logs','wait','stop','kill','rm','exec','cp','top','stats'}

def validate(args, image):
    if not args: raise ValueError('Missing Docker command')
    command = args[0]
    if command in ('run','create'):
        index=1
        while index < len(args):
            argument=args[index]
            if not argument.startswith('-'): break
            flag=argument.split('=',1)[0]
            if flag in VALUE_FLAGS:
                if '=' not in argument:
                    index += 1
                    if index >= len(args): raise ValueError('Missing Docker option value')
                if flag == '--pull' and (argument.split('=',1)[1] if '=' in argument else args[index]) != 'never':
                    raise ValueError('Image pulls are disabled')
            elif flag not in BOOL_FLAGS:
                raise ValueError('Docker option is not approved for offline tasks')
            index += 1
        if index >= len(args) or args[index] != image:
            raise ValueError('Task must use the configured TASK_IMAGE')
        return [command,'--pull=never',*args[1:]]
    if command == 'image' and len(args)>1 and args[1] in ('inspect','ls'):
        return args
    if command in READ_COMMANDS:
        return args
    raise ValueError('Docker operation is disabled for the offline agent')

if __name__=='__main__':
    try:
        args=validate(sys.argv[1:],os.environ['OFFLINE_TASK_IMAGE'])
        os.execv('/usr/bin/docker',['docker',*args])
    except (ValueError,KeyError) as error:
        sys.exit('Offline Docker policy: '+str(error))
