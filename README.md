# snapshot-WebRTC
a simple server for taking snapshots from Janus WebRTC streams

## Installation (Linux and mac)
You must have NodeJS and Python 3.11
```
python3 -m venv venv
source ./venv/bin/activate
pip install -r 'requirements.txt'
cd ./static
npm install
cd ..
```
## Usage
```
source ./venv/bin/activate
python snapshot_server.py
```