#!/usr/bin/env python3
"""
PushDeer notification sender for OpenClaw cron jobs.
Usage: python3 pushdeer_send.py --keys-file /path/to/keys.txt --title "Title" --desp "Content" --type markdown
"""

import argparse
import urllib.request
import urllib.parse
import sys

PUSHDEER_API = "https://api2.pushdeer.com/message/push"

def send_pushdeer(keys, title, desp, msg_type="markdown"):
    """Send notification to PushDeer"""
    results = []
    for key in keys:
        key = key.strip()
        if not key:
            continue
        
        params = {
            "pushkey": key,
            "text": title,
            "desp": desp,
            "type": msg_type
        }
        
        try:
            data = urllib.parse.urlencode(params).encode()
            req = urllib.request.Request(PUSHDEER_API, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = resp.read().decode()
                results.append(f"{key[:20]}...: OK")
        except Exception as e:
            results.append(f"{key[:20]}...: ERROR - {e}")
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Send PushDeer notifications")
    parser.add_argument("--keys-file", required=True, help="Path to file containing PushDeer keys (one per line)")
    parser.add_argument("--title", required=True, help="Notification title")
    parser.add_argument("--desp", required=True, help="Notification content/description")
    parser.add_argument("--type", default="markdown", help="Message type (default: markdown)")
    
    args = parser.parse_args()
    
    # Read keys from file
    try:
        with open(args.keys_file, "r") as f:
            keys = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Keys file not found: {args.keys_file}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading keys file: {e}")
        sys.exit(1)
    
    if not keys:
        print("Error: No keys found in file")
        sys.exit(1)
    
    # Send notifications
    results = send_pushdeer(keys, args.title, args.desp, args.type)
    
    for result in results:
        print(result)
    
    print(f"\nSent to {len(keys)} device(s)")

if __name__ == "__main__":
    main()
