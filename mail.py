#TODO:
# [ ] Prettify Tk interface
# [X] Figure out how/when to batch IMAP requests
# [ ] Work on performance/organizing code
# [ ] Finish implementing mailbox syncing
# [ ] Add support for multiple mailboxes, shown in sidebar
# [ ] Have db contain messages from all labels
# [ ] Unite SQL config table with config.json
# [ ] Determine if SSL is properly implemented/secure
import os, sqlite3, json, re, webbrowser, sys, _tkinter
sys.path.append("services")
from imap import *
from tkinter import *
from tkinter import ttk, messagebox

if sys.platform == "darwin":
    LINK_CURSOR = "pointinghand"
else:
    LINK_CURSOR = "hand1"

def safe_insert(widget, coords, content, tags=("",)):
    try:
        if tags != ("",):
            widget.insert(coords, content, tags)
        else:
            widget.insert(coords, content)
    except _tkinter.TclError:
        #Some characters can't be displayed; char code is out of range
        #Exclude undisplayable chars (a hacky fix, but a simple one!)
        valid_chars = [c for c in content if ord(c) in range(65536)]
        if tags != ("",):
            widget.insert(coords, ''.join(valid_chars), tags)
        else:
            widget.insert(coords, ''.join(valid_chars))
        print("Warning: '" + content, "'has undisplayable chars in it")

class MailboxView:
    """Purpose: Show an interactive list of all messages in a mailbox"""
    def __init__(self, parent, service, label, db_cursor):
        self.parent = parent
        self.service = service
        self.label = label
        self.db_cursor = db_cursor
        self.view = Listbox(self.parent, width=100, height=25)
        self.view.pack(fill=BOTH, expand=1)
        #Need to check if db has data before trying to display messages
        try:
            self.db_cursor.execute("SELECT id FROM messages LIMIT 1")
        except sqlite3.OperationalError:
            self.db_cursor.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, UID INT,"
                                   + " label VARCHAR, date INT, sender VARCHAR,"
                                   + " recipient VARCHAR, subject VARCHAR,"
                                   + " message_text VARCHAR)")
            self.db_cursor.execute("CREATE TABLE drafts (id INTEGER PRIMARY KEY,"
                                   + " recipient VARCHAR, subject VARCHAR,"
                                   + " message_text VARCHAR)")
            self.db_cursor.execute("CREATE TABLE config (key VARCHAR, value INT)")
            self.db_cursor.execute("SELECT id FROM messages LIMIT 1")
        if not self.db_cursor.fetchone():
            self.build_db()
        else:
            self.refresh_db()

        self.titles = []
        self.current_msg = IntVar(value=0)
        self.view.bind("<<ListboxSelect>>", self.switch_current_msg)
        #Place subjects of each message into the Listbox widget
        self.show_subjects()

    def create_msg(self, msg):
        self.db_cursor.execute("INSERT INTO messages (uid, label, date, sender, recipient,"
                               + " subject, message_text) VALUES (?,?,?,?,?,?,?)",
                               (msg["uid"], self.label, msg["internalDate"], msg["from"],
                                msg["to"], msg["subject"], msg["text"]))
    def build_db(self, msg):
        self.last_uid, self.msg_amt = self.service.show_msgs(self.label, "ALL",
                                                             self.create_msg)
        self.db_cursor.execute("INSERT INTO config VALUES (?,?)", ("last_uid", self.last_uid))
        self.db_cursor.execute("INSERT INTO config VALUES (?,?)", ("msg_amt", self.msg_amt))

    def add_updated_msg(self, msg):
        if not self.db_cursor.execute("SELECT id FROM messages WHERE uid = ?",
                                      (msg["uid"],)).fetchone():
            print("Added", msg["uid"])
            self.create_msg(msg)
        else:
            #Do not re-add duplicate messages
            print("Database already has", msg["uid"])

    def refresh_db(self):
        print("Database not rebuilt")
        self.last_uid = self.db_cursor.execute("SELECT value FROM config WHERE key = ?",
                                               ("last_uid",)).fetchone()[0]
        self.msg_amt = self.db_cursor.execute("SELECT value FROM config WHERE key = ?",
                                              ("msg_amt",)).fetchone()[0]
        if self.service.is_synced(self.label, self.last_uid, self.msg_amt):
            print("Database is synced with server")
        else:
            print("Database isn't synced with server")
            criteria = self.service.get_id(self.label, self.last_uid) + b':*'
            self.last_uid, added_msg_amt = self.service.show_msgs(self.label, criteria,
                                                                 self.add_updated_msg)
            self.msg_amt += added_msg_amt
            self.db_cursor.execute("UPDATE config SET value = ? WHERE key = ?",
                                   (self.last_uid, "last_uid"))
            self.db_cursor.execute("UPDATE config SET value = ? WHERE key = ?",
                                   (self.msg_amt, "msg_amt"))
            print("Database now synced")

    def show_subjects(self):
        for id_, subject in self.db_cursor.execute("SELECT id, subject FROM messages WHERE label = ?", (self.label,)):
            safe_insert(self.view, "end", subject)
            #Map index in Listbox to id of message to retrieve
            self.titles.append(id_)

    def get_msg(self, index):
        return self.db_cursor.execute("SELECT date, sender, subject, message_text"
                                      +" FROM messages WHERE id = ? ORDER BY date DESC",
                                      (self.titles[index],)).fetchone()

    def switch_current_msg(self, event):
        #This function implicitly calls MessageView.switch_view() by updating
        #self.current_msg
        #curselection() gives list of selected thread titles; just take 1
        self.current_msg.set(self.view.curselection()[0])

class MessageView:
    """Purpose: Represents text widget at screen bottom; contains text of message(s)
        from currently selected thread in given mailbox"""
    def __init__(self, parent, mailbox):
        self.parent = parent
        self.mailbox = mailbox
        self.view = Text(parent, width=50, height=50, font="TkFixedFont 12", state="disabled")
        self.view.pack(fill=BOTH, expand=1)
        self.view.tag_configure("message_header", font="TkFixedFont 14",
                                foreground="blue", relief="raised")
        self.view.tag_configure("separator", foreground="darkblue",
                                overstrike=True, font="TkFixedFont 25 bold")
        self.view.tag_configure("link", foreground="blue", underline=True)
        self.view.tag_bind("link", "<Enter>", lambda e: self.view.config(cursor=LINK_CURSOR))
        self.view.tag_bind("link", "<Leave>", lambda e: self.view.config(cursor="left_ptr"))
        self.view.tag_bind("link", "<Button-1>", self.open_link)

        #Switch displayed thread when user clicks on threads in ListBox
        self.mailbox.current_msg.trace_add("write", self.switch_view)

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
        index = self.mailbox.current_msg.get()
        self.view.delete("0.0", "end")
        msg = self.mailbox.get_msg(index)
        safe_insert(self.view, "end", f"Date: {msg[0]}\nTo: {USER}\nFrom: {msg[1]}\nSubject: {msg[2]}\n\n", tags=("message_header",))
        safe_insert(self.view, "end", msg[3] + "\n")
        self.view.insert("end", " "*self.view.cget("width") + "\n", ("separator",))
        self.view.configure(state="disabled")
        #Make all URLs in text into clickable links
        for i, row in enumerate(self.view.get("0.0", "end").split("\n")):
            for match in re.finditer(r'<?https?://.+>?(\s|$)', row):
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
        self.inbox = MailboxView(self.parent, self.service, "INBOX", self.db_cursor)
        self.content_view = MessageView(self.parent, self.inbox)
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
