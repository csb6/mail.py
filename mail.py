#TODO:
# [ ] Prettify Tk interface
# [X] Figure out how/when to batch Gmail API requests
# [ ] Work on performance/organizing code
# [X] Wrap up API object/common method calls in a class
# [X] Use threads.list instead of messages.list
# [X] Figure out how to limit message results to inbox
# [X] Set-up/plan tables for sqlite3 database
# [X] Figure out how to orient program around threads, not messages
# [X] Figure out how to update messages table with each thread's msgs/thread_id
# [X] Redesign Gmail API so it's easier to get msgs/threads
# [ ] Figure out how to give unique ids to drafts even when some drafts already in db
import pickle, os, os.path, sqlite3, base64, mimetypes, json, re, webbrowser
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
from apiclient import errors
from tkinter import *
from tkinter import ttk, messagebox

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

    def get_threads(self, labels, maxResults):
        try:
            threads = self.service.users().threads().list(userId='me', labelIds=labels,
                                                          maxResults=maxResults).execute()["threads"]
            batch = self.service.new_batch_http_request()
            for thread in threads:
                batch.add(self.service.users().threads().get(userId='me', id=thread["id"]),
                          callback=lambda id_, res, e, thread=thread: thread.update([("messages", res["messages"])]))
            batch.execute()
            return threads
        except errors.HttpError:
            print("HTTP Error")

    def get_date(self, message):
        headers = message["payload"]["headers"]
        return [pair["value"] for pair in headers if pair["name"].lower() == "date"][0]

    def get_sender(self, message):
        headers = message["payload"]["headers"]
        return [pair["value"] for pair in headers if pair["name"].lower() == "from"][0]

    def get_recipient(self, message):
        headers = message["payload"]["headers"]
        return [pair["value"] for pair in headers if pair["name"].lower() == "to"][0]

    def get_subject(self, message):
        headers = message["payload"]["headers"]
        return [pair["value"] for pair in headers if pair["name"].lower() == "subject"][0]

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

    def print_history_from(self, id_):
        history = self.service.users().history().list(userId='me', startHistoryId=id_, labelId="INBOX", maxResults=10).execute()["history"]
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

class MailboxView:
    """Purpose: Show an interactive list of all messages in a mailbox"""
    def __init__(self, parent, service, labels, db_cursor):
        self.parent = parent
        self.service = service
        self.labels = labels
        self.db_cursor = db_cursor
        self.titles = StringVar(value=[])
        self.view = Listbox(self.parent, width=100, height=25, listvariable=self.titles)
        self.view.pack(fill=BOTH, expand=1)
        #Need to check if db has data before trying to display messages
        try:
            self.db_cursor.execute("SELECT id FROM threads LIMIT 1")
        except sqlite3.OperationalError:
            self.db_cursor.execute("CREATE TABLE threads (db_index INT, id INT, snippet VARCHAR, history_id INT)")
            self.db_cursor.execute("CREATE TABLE messages (id INT, thread_id INT, snippet VARCHAR, date VARCHAR, sender VARCHAR, subject VARCHAR, message_text VARCHAR)")
            self.db_cursor.execute("CREATE TABLE drafts (id INT, recipient VARCHAR, subject VARCHAR, message_text VARCHAR)")
            self.db_cursor.execute("SELECT id FROM threads LIMIT 1")
        if not self.db_cursor.fetchone():
            self.build_db()
        else:
            self.refresh_db()

        self.current_thread = IntVar(value=0)
        self.view.bind("<<ListboxSelect>>", self.switch_current_thread)
        self.service.print_history_from(774246)
        #Place thread snippets (titles, basically) into the Listbox widget
        self.show_threads()

    def build_db(self):
        threads = self.service.get_threads(self.labels, 5)
        #i is the db_index field; used to identify order of threads in mailbox
        for i, thread in enumerate(threads):
            self.db_cursor.execute("INSERT INTO threads VALUES (?,?,?,?)",
                                   (i, thread["id"], thread["snippet"], thread["historyId"]))
            for msg in thread["messages"]:
                #Look at thread-example.py for example of thread dict's layout
                #This ridiculous line accesses the text/plain version of emails
                try:
                    message_text = msg["payload"]["parts"][0]["body"]["data"].strip()
                except KeyError:
                    try:
                        message_text = msg["payload"]["body"]["data"].strip()
                    except KeyError:
                        print("Error: Can't parse email:\n\n", msg)
                        continue
                self.db_cursor.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
                                       (msg["id"], msg["threadId"], msg["snippet"],
                                        self.service.get_date(msg),
                                        self.service.get_sender(msg),
                                        self.service.get_subject(msg), message_text))

    def refresh_db(self):
        print("Database not rebuilt")

    def show_threads(self):
        #Only show first 125 chars as preview of thread so it fits well onscreen
        self.titles.set([t[0][:125] for t in self.db_cursor.execute("SELECT snippet FROM threads")])

    def get_thread_msgs(self, index):
        #fetchall() returns a tuple for each row
        thread_id = self.db_cursor.execute("SELECT id FROM threads WHERE db_index = ?", (index,)).fetchone()[0]
        return [(m[0], m[1], m[2], base64.urlsafe_b64decode(m[3]).decode('utf-8'))
                for m in self.db_cursor.execute("SELECT date, sender, subject, message_text FROM messages WHERE thread_id = ?", (thread_id,))]

    def switch_current_thread(self, event):
        #This function implicitly calls MessageView.switch_view() by updating
        #self.current_thread
        if len(self.titles.get()) != 0:
            #curselection() gives list of selected thread titles; just take 1
            self.current_thread.set(self.view.curselection()[0])

class MessageView:
    """Purpose: Represents text widget at screen bottom; contains text of message(s)
        from currently selected thread in given mailbox"""
    def __init__(self, parent, mailbox):
        self.parent = parent
        self.mailbox = mailbox
        self.view = Text(parent, width=50, height=50, font="TkFixedFont 12", state="disabled")
        self.view.pack(fill=BOTH, expand=1)
        self.view.tag_configure("message_header", font="TkFixedFont 14", foreground="blue", relief="raised")
        self.view.tag_configure("separator", foreground="darkblue", overstrike=True, font="TkFixedFont 25 bold")
        self.view.tag_configure("link", foreground="blue", underline=True)
        self.view.tag_bind("link", "<Button-1>", self.open_link)

        #Switch displayed thread when user clicks on threads in ListBox
        self.mailbox.current_thread.trace_add("write", self.switch_view)

    def open_link(self, event):
        char = self.view.index(f"@{event.x},{event.y}")
        tag = self.view.tag_names(char)
        ranges = [str(i) for i in self.view.tag_ranges(tag)]
        char_line, char_letter = [int(n) for n in char.split(".")]
        #Look at every second index; will give end-bound of link's location
        for i in range(1, len(ranges), 2):
            line, letter = [int(n) for n in ranges[i].split(".")]
            if line >= char_line and letter >= char_letter:
                start, end = ranges[i-1], ranges[i]
                break
        webbrowser.open_new_tab(self.view.get(start, end).strip().strip("<>"))

    def switch_view(self, name, index, mode):
        self.view.configure(state="normal")
        index = self.mailbox.current_thread.get()
        self.view.delete("0.0", "end")
        msgs = self.mailbox.get_thread_msgs(index)
        for msg in msgs:
            self.view.insert("end", f"Date: {msg[0]}\nTo: {USER}\nFrom: {msg[1]}\nSubject: {msg[2]}\n\n", ("message_header",))
            self.view.insert("end", msg[3] + "\n")
            self.view.insert("end", " "*self.view.cget("width") + "\n", ("separator",))
        self.view.configure(state="disabled")
        #Make all URLs in text into clickable links
        for i, row in enumerate(self.view.get("0.0", "end").split("\n")):
            for match in re.finditer(r'<?https?://.+>?', row):
                self.view.tag_add("link", f"{i+1}.{match.start()}", f"{i+1}.{match.end()}")

class App:
    def __init__(self, parent):
        self.parent = parent
        compose = Button(self.parent, text="Compose")
        compose.bind("<Button-1>", lambda e: self.compose_msg())
        compose.pack(ipadx=5)
        self.service = MailService()
        self.db = sqlite3.connect('mail.db')
        self.db_cursor = self.db.cursor()
        self.inbox = MailboxView(self.parent, self.service, ["INBOX"], self.db_cursor)
        self.content_view = MessageView(self.parent, self.inbox)
        self.draft_id = 0
        #Add code to close db, db_cursor when app shuts down

    def send_msg(self):
        text = self.compose_area.get("1.0", "end").strip()
        to = self.to_line.get()
        subject = self.subject_line.get()
        if self.service.send_msg(to, subject, text):
            messagebox.showinfo(message="Email sent successfully")
            self.win.destroy()
        else:
            messagebox.showinfo(message="Error: Email failed to send")

    def save_draft(self):
        to = self.to_line.get()
        subject = self.subject_line.get()
        text = self.compose_area.get("1.0", "end")
        try:
            self.db_cursor.execute("INSERT INTO drafts VALUES (?,?,?,?)",
                                   (self.draft_id, to, subject, text))
        except sqlite3.Error:
            messagebox.showinfo(message="Error: Draft failed to save")
        else:
            messagebox.showinfo(message="Draft saved successfully")
            self.draft_id += 1
            self.win.destroy()

    def compose_msg(self):
        self.win = Toplevel(self.parent)
        self.win.title("Compose Message")
        send = Button(self.win, text="Send")
        send.bind("<Button-1>", lambda e: self.send_msg())
        send.pack(ipadx=5)
        save = Button(self.win, text="Save As Draft")
        save.bind("<Button-1>", lambda e: self.save_draft())
        save.pack(ipadx=5)

        Label(self.win, text="To:").pack()
        self.to_line = Entry(self.win)
        self.to_line.pack()
        Label(self.win, text="Subject:").pack()
        self.subject_line = Entry(self.win)
        self.subject_line.pack()
        self.compose_area = Text(self.win, width=30, height=30, font="TkFixedFont")
        self.compose_area.pack(fill=BOTH, expand=1)

    def cleanup_db(self):
        self.db.commit()
        self.db_cursor.close()
        self.db.close()
        print("Database successfully shutdown")

def main():
    root = Tk()
    root.title("Email Client")
    app = App(root)
    root.mainloop()
    app.cleanup_db()

main()
