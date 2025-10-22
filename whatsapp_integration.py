import os
import requests
import json
from datetime import datetime, timedelta


GRAPH_API_BASE = "https://graph.facebook.com/v17.0"


class WhatsAppClient:
    def __init__(self,
                 access_token: str | None = None,
                 phone_number_id: str | None = None):
        self.access_token = access_token or os.environ.get("ACCESS_TOKEN", "")
        self.phone_number_id = phone_number_id or os.environ.get("PHONE_NUMBER_ID", "")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def send_text(self, to_number: str, message: str) -> tuple[int, dict]:
        """
        Send a plain text WhatsApp message.
        to_number: E.164 format without symbols, e.g. "15551234567"
        Returns (status_code, response_json)
        """
        # Testing mode: redirect all messages to test number
        testing_mode = os.environ.get("TESTING_MODE", "false").lower() == "true"
        original_number = to_number
        if testing_mode:
            to_number = "8801791961885"
            print(f"[WHATSAPP TEST MODE] Redirecting message from {original_number} to {to_number}")
        
        url = f"{GRAPH_API_BASE}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message},
        }
        print(f"[WHATSAPP SEND] to={to_number} phone_number_id={self.phone_number_id}")
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=20)
        try:
            response_data = resp.json()
            print(f"[WHATSAPP RESP] status={resp.status_code} body={response_data}")
            
            # Check for token expiration
            if resp.status_code == 401 and 'error' in response_data:
                error = response_data['error']
                if error.get('code') == 190 and 'expired' in error.get('message', '').lower():
                    print(f"[WHATSAPP ERROR] Access token expired: {error['message']}")
                    print(f"[WHATSAPP ERROR] Please generate a new token from Meta App Dashboard")
                    print(f"[WHATSAPP ERROR] Go to: https://developers.facebook.com/apps/")
                    
            return resp.status_code, response_data
        except Exception:
            return resp.status_code, {"raw": resp.text}

    def send_template(self, to_number: str, template_name: str, language_code: str = "en_US", components: list | None = None) -> tuple[int, dict]:
        """
        Send a pre-approved WhatsApp template message (required outside 24h window).
        components: optional list per Cloud API spec.
        """
        # Testing mode: redirect all messages to test number
        testing_mode = os.environ.get("TESTING_MODE", "false").lower() == "true"
        original_number = to_number
        if testing_mode:
            to_number = "8801791961885"
            print(f"[WHATSAPP TEST MODE] Redirecting template from {original_number} to {to_number}")
        
        url = f"{GRAPH_API_BASE}/{self.phone_number_id}/messages"
        payload: dict = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components
        print(f"[WHATSAPP SEND TEMPLATE] to={to_number} template={template_name}")
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=20)
        try:
            response_data = resp.json()
            print(f"[WHATSAPP RESP TEMPLATE] status={resp.status_code} body={response_data}")
            return resp.status_code, response_data
        except Exception:
            return resp.status_code, {"raw": resp.text}


# Convenience function for backward compatibility
def send_whatsapp_message(to_number: str, message: str) -> None:
    """
    Send a WhatsApp message using the default client.
    This function maintains backward compatibility with existing code.
    """
    client = WhatsAppClient()
    status_code, response = client.send_text(to_number, message)
    
    if status_code == 200:
        print(f"[WHATSAPP REPLY] {status_code} {response}")
    else:
        print(f"[WHATSAPP ERROR] {status_code} {response}")


def send_template_message(to_number: str, template_name: str, language_code: str = "en_US", components: list = None) -> tuple[int, dict]:
    """
    Send a WhatsApp template message using the default client.
    Returns (status_code, response) for error handling.
    """
    client = WhatsAppClient()
    return client.send_template(to_number, template_name, language_code, components)


# Notification templates and functions
def send_match_reminder(team_phone: str, team_name: str, opponent_name: str) -> tuple[int, dict]:
    """Send 24h match reminder template"""
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": team_name},
                {"type": "text", "text": opponent_name}
            ]
        }
    ]
    return send_template_message(team_phone, "match_reminder", components=components)


def send_new_round_notification(team_phone: str, team_name: str, round_number: int, opponent_name: str) -> tuple[int, dict]:
    """Send new round notification template (opponent contact info available via secure link)"""
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": team_name},
                {"type": "text", "text": str(round_number)},
                {"type": "text", "text": opponent_name}
            ]
        }
    ]
    return send_template_message(team_phone, "new_round", components=components)


def send_walkover_warning(team_phone: str, team_name: str, opponent_name: str, hours_remaining: int) -> tuple[int, dict]:
    """Send walkover countdown warning template"""
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": team_name},
                {"type": "text", "text": opponent_name},
                {"type": "text", "text": str(hours_remaining)}
            ]
        }
    ]
    return send_template_message(team_phone, "walkover_warning", components=components)


