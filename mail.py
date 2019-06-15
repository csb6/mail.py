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
import os, sqlite3, json, re, webbrowser, sys
sys.path.append("services")
from imap import *
from tkinter import *
from tkinter import ttk, messagebox

if sys.platform == "darwin":
    LINK_CURSOR = "pointinghand"
else:
    LINK_CURSOR = "hand1"

class MailboxView:
    """Purpose: Show an interactive list of all messages in a mailbox"""
    def __init__(self, parent, service, label, db_cursor):
        self.parent = parent
        self.service = service
        self.label = label
        self.db_cursor = db_cursor
        self.titles = StringVar(value=[])
        self.view = Listbox(self.parent, width=100, height=25, listvariable=self.titles)
        self.view.pack(fill=BOTH, expand=1)
        #Need to check if db has data before trying to display messages
        try:
            self.db_cursor.execute("SELECT id FROM messages LIMIT 1")
        except sqlite3.OperationalError:
            self.db_cursor.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY,"
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

        self.current_msg = IntVar(value=0)
        self.view.bind("<<ListboxSelect>>", self.switch_current_msg)
        #Place subjects of each message into the Listbox widget
        self.show_subjects()

    def build_db(self):
        messages = self.service.get_msgs(self.label, "SINCE 11-May-2019")
        for msg in messages:
            self.db_cursor.execute("INSERT INTO messages (label, date, sender, recipient,"
                                   + " subject, message_text) VALUES (?,?,?,?,?,?)",
                                   (self.label, msg["internalDate"], msg["from"],
                                    msg["to"], msg["subject"], msg["text"]))

    def refresh_db(self):
        print("Database not rebuilt")

    def show_subjects(self):
        #Only show first 125 chars as preview of thread so it fits well onscreen
        self.titles.set([m[0][:125] for m in self.db_cursor.execute("SELECT subject FROM messages WHERE label = ?", (self.label,))])

    def get_msg(self, index):
        return self.db_cursor.execute("SELECT date, sender, subject, message_text"
                                      +" FROM messages m WHERE id = ? ORDER BY date DESC",
                                      (index+1,)).fetchone()

    def switch_current_msg(self, event):
        #This function implicitly calls MessageView.switch_view() by updating
        #self.current_msg
        if len(self.titles.get()) != 0:
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
        self.view.insert("end", f"Date: {msg[0]}\nTo: {USER}\nFrom: {msg[1]}\nSubject: {msg[2]}\n\n", ("message_header",))
        self.view.insert("end", msg[3] + "\n")
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
