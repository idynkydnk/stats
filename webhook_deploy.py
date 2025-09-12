import os
import subprocess

def deploy():
    os.chdir('/home/idynkydnk/stats')
    subprocess.run(['git', 'pull'], check=True)
    subprocess.run(['touch', '/var/www/idynkydnk_pythonanywhere_com_wsgi.py'], check=True)
    return "Deployment successful"
