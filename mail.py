#TODO:
# [ ] Prettify Tk interface
# [X] Figure out how/when to batch IMAP requests
# [ ] Work on performance/organizing code
# [X] Finish implementing mailbox syncing
# [ ] Add support for multiple mailboxes, shown in sidebar
# [ ] Have db contain messages from all labels
# [ ] Unite SQL config table with config.json
# [ ] Determine if SSL is properly implemented/secure
# [X] Change MailService.is_synced() to sync_status, returning
#     info about if synced (if not, say how many messages added/deleted)
# [ ] Add code for switching MailboxControllers; make sure to disable
#     trace_add() bindings for inactive controllers
import os, sqlite3, json, re, webbrowser, sys, _tkinter
sys.path.append("services")
from imap import *
from tkinter import *
from tkinter import ttk, messagebox

if sys.platform == "darwin":
    LINK_CURSOR = "pointinghand"
else:
    LINK_CURSOR = "hand1"

def safe_insert(widget, coords, content, tags=tuple()):
    #Acts like TextWidget.insert(), but ensures that only characters
    #which Tk can display are in the inserted string
    try:
        if tags:
            widget.insert(coords, content, tags)
        else:
            widget.insert(coords, content)
    except _tkinter.TclError:
        #Some characters can't be displayed; char code is out of range
        #Exclude undisplayable chars (a hacky fix, but a simple one!)
        valid_chars = [c for c in content if ord(c) in range(65536)]
        if tags:
            widget.insert(coords, ''.join(valid_chars), tags)
        else:
            widget.insert(coords, ''.join(valid_chars))
        print("Warning: '" + content + "' has undisplayable chars in it")

class MailboxView:
    """Purpose: Show an interactive list of all messages in a mailbox"""
    def __init__(self, parent):
        self.parent = parent
        #The large widget listing subjects of all messages in mailbox
        self.widget = Listbox(self.parent, width=100, height=25)
        self.widget.pack(fill=BOTH, expand=1)
        #The list of db primary keys for emails onscreen; index is result of curselection
        self.ids = []
        self.widget.bind("<<ListboxSelect>>", self.switch_current_msg)
        #The index of the currently-selected email; switch_current_msg called when changed
        self.current_msg = IntVar(value=0)

    def switch_current_msg(self, event):
        #This function implicitly calls MailboxController.switch_msg_view() by
        #updating self.current_msg
        #curselection() gives list of selected thread titles; just take 1
        self.current_msg.set(self.widget.curselection()[0])

class MailboxController:
    """Purpose: Show an interactive list of all messages in a mailbox"""
    def __init__(self, parent, service, label, db_cursor):
        #The Tk object that all widgets in this object are children of
        self.parent = parent
        #The email service protocol object (e.g. for IMAP) used to get/send emails
        self.service = service
        #The mailbox name on the server
        self.label = label
        #The local database file used to store emails/other data
        self.db_cursor = db_cursor
        #The large widget listing subjects of all messages in mailbox
        self.list_view = MailboxView(self.parent)
        #The text widget for displaying individual messages
        self.msg_view = MessageView(self.parent)
        #Need to check if db has data before trying to display messages
        try:
            self.db_cursor.execute("SELECT id FROM messages LIMIT 1")
        except sqlite3.OperationalError:
            self.db_cursor.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, UID INT,"
                                   + " label VARCHAR, date INT, sender VARCHAR,"
                                   + " recipient VARCHAR, subject VARCHAR,"
                                   + " type VARCHAR, message_text VARCHAR)")
            self.db_cursor.execute("CREATE TABLE drafts (id INTEGER PRIMARY KEY,"
                                   + " recipient VARCHAR, subject VARCHAR,"
                                   + " message_text VARCHAR)")
            self.db_cursor.execute("CREATE TABLE config (key VARCHAR, value INT)")
            self.db_cursor.execute("SELECT id FROM messages LIMIT 1")
        if not self.db_cursor.fetchone():
            self.build_db()
        else:
            self.refresh_db()

        #Switch displayed message when user clicks on subject in ListBox
        self.list_view.current_msg.trace_add("write", self.switch_msg_view)
        #Place subjects of each message into the Listbox widget
        self.show_subjects()

    def create_msg(self, msg):
        #Callback passed to MailService.show_msgs(); adds new msgs to database
        self.db_cursor.execute("INSERT INTO messages (uid, label, date, sender, recipient,"
                               + " subject, type, message_text) VALUES (?,?,?,?,?,?,?,?)",
                               (msg["uid"], self.label, msg["internalDate"], msg["from"],
                                msg["to"], msg["subject"], msg["type"], msg["text"]))

    def build_db(self):
        #Adds all messages from current mailbox to db
        self.last_uid, self.msg_amt = self.service.show_msgs(self.label, "ALL",
                                                             self.create_msg)
        self.db_cursor.execute("INSERT INTO config VALUES (?,?)", ("last_uid", self.last_uid))
        self.db_cursor.execute("INSERT INTO config VALUES (?,?)", ("msg_amt", self.msg_amt))

    def add_updated_msg(self, msg):
        #Callback passed to MailService.show_msgs(); adds only new msgs to db
        if not self.db_cursor.execute("SELECT id FROM messages WHERE uid = ?",
                                      (msg["uid"],)).fetchone():
            print("Added", msg["uid"])
            self.create_msg(msg)
        else:
            #Do not re-add duplicate messages
            print("Database already has", msg["uid"])

    def refresh_db(self):
        #Updates database with changes since last sync
        print("Database not rebuilt")
        self.last_uid = self.db_cursor.execute("SELECT value FROM config WHERE key = ?",
                                               ("last_uid",)).fetchone()[0]
        self.msg_amt = self.db_cursor.execute("SELECT value FROM config WHERE key = ?",
                                              ("msg_amt",)).fetchone()[0]
        is_synced, server_msg_amt, new_msgs = self.service.sync_status(self.label, self.last_uid,
                                                                       self.msg_amt)
        if is_synced and not new_msgs:
            print("Database is synced with server")
        else:
            print("Database isn't synced with server")
            #Add any new messages if needed
            if new_msgs:
                #Make list of msgs to attempt to show; ex: b'2417,2418,2419'
                criteria = b','.join(new_msgs)
                self.last_uid = self.service.show_msgs(self.label, criteria,
                                                       self.add_updated_msg)

            #Verify all messages currently in database as present on server
            server_uids = self.service.get_all_uids(self.label)
            for id_, client_uid in self.db_cursor.execute("SELECT id, uid FROM messages WHERE label = ?", (self.label,)):
                #Remove any messages that the server removed since last sync
                if client_uid not in server_uids:
                    self.db_cursor.execute("DELETE FROM messages WHERE label = ? AND uid = ?",
                                           (self.label, client_uid))
                    print("Removed", client_uid)

            assert len(self.db_cursor.execute("SELECT id FROM messages WHERE label = ?",
                                              (self.label,)).fetchall()) == len(server_uids), "Number of messages on server not matching number of ids on client"
            assert len(server_uids) == server_msg_amt

            self.msg_amt = server_msg_amt
            self.db_cursor.execute("UPDATE config SET value = ? WHERE key = ?",
                                   (self.last_uid, "last_uid"))
            self.db_cursor.execute("UPDATE config SET value = ? WHERE key = ?",
                                   (self.msg_amt, "msg_amt"))
            print("Database now synced")

    def show_subjects(self):
        #Fills Listbox with subjects of each message
        for id_, subject in self.db_cursor.execute("SELECT id, subject FROM messages WHERE label = ?", (self.label,)):
            #Insert with small margin on left
            safe_insert(self.list_view.widget, "end", "  "+subject)
            #Map index in Listbox to id of message to retrieve
            self.list_view.ids.append(id_)

    def switch_msg_view(self, name, i, mode):
        index = self.list_view.current_msg.get()
        msg = self.db_cursor.execute("SELECT date, recipient, sender, subject, message_text"
                                     +" FROM messages WHERE id = ? ORDER BY date DESC",
                                     (self.list_view.ids[index],)).fetchone()
        self.msg_view.show(msg)

class MessageView:
    """Purpose: Represents text widget at screen bottom; contains text of message(s)
        from currently selected thread in given mailbox"""
    def __init__(self, parent):
        self.parent = parent
        self.widget = Text(parent, width=50, height=50, font="TkFixedFont 12", state="disabled")
        self.widget.pack(fill=BOTH, expand=1)
        self.widget.tag_configure("message_header", font="TkFixedFont 14",
                                  foreground="blue", relief="raised")
        self.widget.tag_configure("separator", foreground="darkblue",
                                  overstrike=True, font="TkFixedFont 25 bold")
        self.widget.tag_configure("link", foreground="blue", underline=True)
        self.widget.tag_bind("link", "<Enter>", lambda e: self.widget.config(cursor=LINK_CURSOR))
        self.widget.tag_bind("link", "<Leave>", lambda e: self.widget.config(cursor="left_ptr"))
        self.widget.tag_bind("link", "<Button-1>", self.open_link)

    def open_link(self, event):
        char = self.widget.index(f"@{event.x},{event.y}")
        tag = self.widget.tag_names(char)
        ranges = [str(i) for i in self.widget.tag_ranges(tag)]
        char_line, char_letter = [int(n) for n in char.split(".")]
        #Look at every second index; will give end-bound of link's location
        for i in range(1, len(ranges), 2):
            line, letter = [int(n) for n in ranges[i].split(".")]
            if line >= char_line and letter >= char_letter:
                start, end = ranges[i-1], ranges[i]
                break
        webbrowser.open_new_tab(self.widget.get(start, end).strip().strip("<>()"))

    def show(self, msg):
        self.widget.configure(state="normal")
        self.widget.delete("0.0", "end")
        safe_insert(self.widget, "end", f"Date: {msg[0]}\nTo: {msg[1]}\nFrom: {msg[2]}\nSubject: {msg[3]}\n\n", tags=("message_header",))
        safe_insert(self.widget, "end", msg[4] + "\n")
        self.widget.insert("end", " "*self.widget.cget("width") + "\n", ("separator",))
        self.widget.configure(state="disabled")
        #Make all URLs in text into clickable links
        for i, row in enumerate(self.widget.get("0.0", "end").split("\n")):
            for match in re.finditer(r'<?https?://[^\s]+>?((?<!\s)|$)', row):
                self.widget.tag_add("link", f"{i+1}.{match.start()}", f"{i+1}.{match.end()}")

class App:
    def __init__(self, parent):
        self.parent = parent
        compose = Button(self.parent, text="Compose")
        compose.bind("<Button-1>", lambda e: self.compose_msg())
        compose.pack(ipadx=5)
        self.service = MailService()
        self.db = sqlite3.connect('mail.db')
        self.db_cursor = self.db.cursor()
        self.inbox = MailboxController(self.parent, self.service, "INBOX", self.db_cursor)
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
            self.db_cursor.execute("INSERT INTO drafts (recipient, subject, message_text)"
                                   + " VALUES (?,?,?)", (to, subject, text))
        except sqlite3.Error:
            messagebox.showinfo(message="Error: Draft failed to save")
        else:
            messagebox.showinfo(message="Draft saved successfully")
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
