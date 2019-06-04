import os.path, pickle, datetime, base64
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
from apiclient import errors
# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.compose',
          "https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.insert"]
USER = "csboreo66@gmail.com"

class MailService:
    def __init__(self):
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server()
                # Save the credentials for the next run
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)

        self.service = build('gmail', 'v1', credentials=creds)

    def get_message(self, raw_msg):
        #Look at thread-example.py for example raw_msg's layout in "messages":[]
        msg = {}
        headers = raw_msg["payload"]["headers"]
        for k in ("id", "threadId", "labelIds", "snippet", "historyId"):
            msg[k] = raw_msg[k]
        msg["internalDate"] = int(raw_msg["internalDate"])
        msg["from"] = [pair["value"] for pair in headers if pair["name"].lower() == "from"][0]
        msg["to"] = [pair["value"] for pair in headers if pair["name"].lower() == "to"][0]
        msg["subject"] = [pair["value"] for pair in headers if pair["name"].lower() == "subject"][0]
        try:
            msg["text"] = raw_msg["payload"]["parts"][0]["body"]["data"].strip()
        except KeyError:
            msg["text"] = raw_msg["payload"]["body"]["data"].strip()
        return msg

    def add_thread_msgs(self, res, thread):
        thread["messages"] = []
        for raw_msg in res["messages"]:
                try:
                    msg = self.get_message(raw_msg)
                except KeyError:
                    print("Error: Can't parse email:\n\n", raw_msg)
                    continue
                thread["messages"].append(msg)

    def get_threads(self, labels, maxResults):
        try:
            threads = self.service.users().threads().list(userId='me', labelIds=labels,
                                                          maxResults=maxResults).execute()["threads"]
            batch = self.service.new_batch_http_request()
            for thread in threads:
                batch.add(self.service.users().threads().get(userId='me', id=thread["id"]),
                          callback=lambda id_, res, e, thread=thread: self.add_thread_msgs(res, thread))
            batch.execute()
            return threads
        except errors.HttpError:
            print("HTTP Error")

    def get_date(self, internalDate):
        #Use only when displaying date onscreen; db should only store timestamp
        date = datetime.datetime.fromtimestamp(internalDate / 1000)
        return date.ctime()

    def send_msg(self, to, subject, text):
        msg = MIMEText(text)
        msg["to"], msg["from"], msg["subject"] = to, "me", subject
        #Must convert msg str to b-string, then base64 encode, then back to str type
        body = {"raw": base64.urlsafe_b64encode(msg.as_string().encode()).decode("utf-8")}
        try:
            self.service.users().messages().send(userId='me', body=body).execute()
            return True
        except errors.HttpError:
            print("Error Sending")
            return False

    def get_curr_history_id(self, curr_id, label):
        return self.service.users().history().list(userId='me', startHistoryId=curr_id, labelId=label, maxResults=1).execute()["historyId"]

    def is_synced(self, curr_id, label):
        print("Current id:", curr_id, "Mailbox id:", self.get_curr_history_id(curr_id, label))
        return self.get_curr_history_id(curr_id, label) == curr_id

    def get_mail_diff(self, curr_id, label):
        history = self.service.users().history().list(userId='me', startHistoryId=curr_id, labelId=label).execute()
        added, deleted, label_added, label_removed = [], [], [], []
        batch = self.service.new_batch_http_request()
        for record in history["history"]:
            if "messagesAdded" in record:
                for i, header in enumerate(record["messagesAdded"]):
                    #added.append(header["message"]["id"])
                    batch.add(self.service.users().messages().get(userId='me', id=header["message"]["id"]), callback=lambda id_, res, e, added=added: added.insert(i, self.get_message(res)))
            if "messagesDeleted" in record:
                for header in record["messagesDeleted"]:
                    deleted.append(header["message"]["id"])
            if "labelsAdded" in record:
                for header in record["labelsAdded"]:
                    diff = (header["message"]["id"], header["labelIds"])
                    label_added.append(diff)
            if "labelsRemoved" in record:
                for header in record["labelsRemoved"]:
                    diff = (header["message"]["id"], header["labelIds"])
                    label_removed.append(diff)
        batch.execute()
        return added, deleted, label_added, label_removed

    def print_history_from(self, id_):
        history = self.service.users().history().list(userId='me', startHistoryId=id_, labelId="INBOX").execute()["history"]
        for record in history:
            if not any([i in record for i in ["messagesAdded", "messagesDeleted",
                                              "labelsAdded", "labelsRemoved"]]):
                continue
            print("Record with ID", record["id"], ":")
            if "messagesAdded" in record:
                print(" ADDED:")
                for msg in record["messagesAdded"]:
                    head = msg["message"]
                    print("  Message with id", head["id"], "in thread with id",
                          head["threadId"])
            if "messagesDeleted" in record:
                print(" DELETED:")
                for msg in record["messagesDeleted"]:
                    head = msg["message"]
                    print("  Message with id", head["id"], "in thread with id",
                          head["threadId"])
            if "labelsAdded" in record:
                print("  ADDED LABELS TO:")
                for msg in record["labelsAdded"]:
                    head = msg["message"]
                    print(" Message with id", head["id"], "in thread with id",
                          head["threadId"], "had labels", msg["labelIds"], "added")
            if "labelsRemoved" in record:
                print(" REMOVED LABELS FROM:")
                for msg in record["labelsRemoved"]:
                    head = msg["message"]
                    print("  Message with id", head["id"], "in thread with id",
                          head["threadId"], "had labels", msg["labelIds"], "removed")
