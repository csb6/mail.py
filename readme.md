# mail.py

A fairly basic email client written in Python supporting IMAP/SMTP. It is currently a work in progress and is not ready for use.

## Requirements

- All dependencies are part of the Python standard library. On Mac/Windows platforms, no additional packages need to be installed.

- However, Tkinter (the GUI toolkit used) must be installed separately on Linux.
As of right now, I have no ability to test the program on a Linux machine, but
it should be fairly simple to install Python and Tk using your system's
package manager.
https://stackoverflow.com/questions/4783810/install-tkinter-for-python has
more information on Linux installation.

## Usage

- After cloning, create a file named `config.json` with the following structure:
```
{
     "host": "",
     "username": "",
     "password": ""
}
```

- Look up the hostname for your email provider, then fill out the JSON file.

- For Gmail addresses with 2-Step Verification, you need to create an
app-specific password. Go to https://myaccount.google.com/security
and create a password. Copy this password into the JSON.

- Currently, there is support for downloading your inbox, displaying
the emails onscreen, adding/removing new messages since the last sync, and
sending emails by clicking on the `Compose` button at the
top of the screen. The messages are stored in a local database file, `mail.db`, which you can freely delete in order to rebuild your inbox.

- This program is not currently in a fully usable state, so core features like email syncing, multiple mailboxes, and drafts are not fully implemented.
