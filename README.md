# Reward Max agent for code challenge

## Run guide

### Requirements
- python3.5+
- install packages in requirements.txt

### Entry point
Run `python server.py` inside this package, the api is then accessible in localhost:9090

### Example
- name: `curl -H "Content-Type: application/json" -d "" localhost:9090/name`
- move: `curl -H "Content-Type: application/json" -d @sample.json localhost:9090/move`
