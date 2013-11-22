This is a simple server that shows the size of each directory.

How to use
----------

Launch an EC2 instance (AMI: default amazon linux 64-bit)
sudo su
yum install -y gcc-c++
yum install -y libxml2-python libxml2-devel
yum install -y python-devel
yum install -y openssl-devel
sudo yum install -y git
easy_install uwsgi
easy_install Flask
easy_install pip
pip install dropbox
pip install pyopenssl

Download and run the server:
git clone git@github.com:tjhunter/tjhunter-db-assignment.git
cd tjhunter-db-assignment
python simple_dropbox_app

The server will be running using https on port 5000.
