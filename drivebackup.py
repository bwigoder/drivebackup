import datetime
import ConfigParser
import sys
import time
from PyQt4 import QtGui, Qt, QtCore
import webbrowser
import logging
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.client import FlowExchangeError
from apiclient.discovery import build
from apiclient import errors
import httplib2
import pickle
import os

class DriveBackup():
	def __init__(self):
		logging.basicConfig()

		# The app, window + config file objects need to be accessible globally
		global app, w, config_file

		msg = PrintOut('Welcome to DriveBackup', 'header')
		config_file = DbConfig()

		# Application object
		app = QtGui.QApplication(sys.argv)
		app.setWindowIcon(QtGui.QIcon(os.path.join('images', 'folder.png')))

		# Create a window (a "widget" with no parent)
		w = QtGui.QWidget()

		# Set window dimensions
		w.setFixedSize(600, 400)

		# Set window position (center)
		screen = QtGui.QDesktopWidget().screenGeometry()
		size = w.geometry()
		w.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)

		# Set window Title
		w.setWindowTitle('DriveBackup ' + config_file.version)

		# Load start screen
		layout = Screen()
		layout.initUI("start")

		# Add status of config file
		layout.setStatus(config_file.status)

		# Show window
		w.show()
		
		# Exit when the window is destroyed
		sys.exit(app.exec_())

class Screen(QtGui.QWidget):
	def __init__(self):
		super(Screen, self).__init__()

	def initUI(self, choose_screen):
		if choose_screen == 'start':
			# Welcome message
			self.welcome_msg = QtGui.QLabel(w)
			self.welcome_msg.setText('Welcome to DriveBackup!')
			self.welcome_msg.setStyleSheet('font-size: 18pt; text-align: center;')
			self.welcome_msg.setAlignment(QtCore.Qt.AlignHCenter)
			self.welcome_msg.setMaximumHeight(25)

			# Status bar
			#self.status_lbl = QtGui.QLabel(w)
			#self.status_lbl.setText('Status:')
			self.status_msg = QtGui.QPlainTextEdit(w)
			self.status_msg.setReadOnly(True)
			self.status_msg.setMaximumHeight(90)
			self.setStatus("DriveBackup Initiated.")

			# Authenticate Button
			self.add_account_btn = Qt.QPushButton("Add Account", w)
			self.add_account_btn.setFixedWidth(150)
			app.connect(self.add_account_btn, Qt.SIGNAL("clicked()"), self.chooseAuth)

			# Place objects on screen
			self.master = QtGui.QVBoxLayout()
			self.master.addWidget(self.welcome_msg)

			self.action_bar = QtGui.QGridLayout()

			# List accounts
			self.updateAccountsList()
			self.action_bar.addWidget(self.add_account_btn, 0, 1)

			# Account info area
			self.select_files_msg = QtGui.QLabel()
			self.select_files_msg.setText('Select files + folders for automated backup:')

			self.acc_info = QtGui.QGridLayout()
			self.file_list = Qt.QListView(self)
			self.file_list.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
			self.file_list.setMaximumSize(QtCore.QSize(16777215, 150))
			self.file_list.setAlternatingRowColors(True)
			self.file_model = Qt.QStandardItemModel(self.file_list)

			# Get files
			self.updateFileList()

			self.acc_info.addWidget(self.select_files_msg)
			self.acc_info.addWidget(self.file_list)

			self.status_area = QtGui.QGridLayout()
			self.status_area.addWidget(self.status_msg, 1, 0)

			self.master.addLayout(self.action_bar)
			self.master.addLayout(self.acc_info)
			self.master.addLayout(self.status_area)
			w.setLayout(self.master)

		elif choose_screen == 'add_account':
			# Create form to login to Google Account
			self.add_account_title = QtGui.QLabel(w)
			self.add_account_title.setText('Add Google Account')

			self.email_address_lbl = QtGui.QLabel(w)
			self.email_address_lbl.setText('Google Email Address')
			self.email_address = QtGui.QTextEdit(w)

			ret = QtGui.QMessageBox.information(self, "Add Account", "We'll now open your browser so that you can authorize DriveBackup to access your account.\n\nDriveBackup will only request READONLY access to your files.", QtGui.QMessageBox.Ok, QtGui.QMessageBox.Cancel)

			if ret == QtGui.QMessageBox.Ok:
				# Prompt user to authorize Google Drive in browser
				self.session = Auth()
				self.session.login()

				# Now ask user to enter auth code
				auth_code, ok_auth_code = QtGui.QInputDialog.getText(self, 'Add Account', 'Enter the authentication code provided by Google', QtGui.QLineEdit.Normal, '')
				if ok_auth_code and len(auth_code) > 0:
					self.session.store_auth(auth_code)

					# Log results to console
					self.setStatus(self.session.status)

					# Update account list
					self.updateAccountsList()

	def updateAccountsList(self):
		self.accounts_list = QtGui.QComboBox(self)
		
		# Remove current items
		self.accounts_list.clear()

		# Add blank item
		self.accounts_list.addItem('Please select an account.', '')

		# Add items from config
		for i in config_file.Config.sections():
			if i[:7] == 'Account':
				# Check a config file exists
				if os.path.isfile(os.path.join('userdata' , 'creds_' + i[8:])):
					self.accounts_list.addItem(config_file.Config.get(i, 'user_email') +  ' (' + config_file.Config.get(i, 'user_name') + ')', i[8:])
				else:
					self.setStatus ('Userdata file for account ' + config_file.Config.get(i, 'user_email') + ' is missing!')
					config_file.Config.remove_section(i)
					self.setStatus ('Removed account ' + config_file.Config.get(i, 'user_email') + ' from config.')

		# Remove widget + re-add it
		self.action_bar.removeWidget(self.accounts_list)
		self.action_bar.addWidget(self.accounts_list, 0, 0)

		# Set a signal to reload files on change
		self.connect(self.accounts_list, QtCore.SIGNAL("currentIndexChanged(const QString&)"), self.updateFileList)

	def updateFileList(self):
		# Get selected account/user ID
		selected_item_in_list = self.accounts_list.currentIndex()
		selected_user_id = str(self.accounts_list.itemData(selected_item_in_list).toString())
		
		# Remove all files in list
		self.file_model.clear()

		# Connect to this account, if there is an account
		if len(selected_user_id) > 0:
			filehandler = open(os.path.join('userdata' , 'creds_' + selected_user_id), 'r')

			self.session = Auth()
			self.session.credentials = pickle.load(filehandler)
			self.session.connect_to_account()

			file_list = []
			folder_list = []
			page_token = None
			while True:
				try:
					param = {}
					param['q'] = "'root' in parents"
					if page_token:
						param['pageToken'] = page_token
					# Google returns files and folders without discriminating
					files = self.session.drive_service.files().list(**param).execute()

					# Determine if each item is a file or folder, and add to the appropriate list
					filesAndFolders = files['items']
					for item in filesAndFolders:
						if item['mimeType'] == 'application/vnd.google-apps.folder':
							folder_list.append(item)
						else:
							file_list.append(item)

					page_token = files.get('nextPageToken')
					if not page_token:
						break
				except errors.HttpError, error:
					print 'An error occurred: %s' % error
					break

			# Sort files + folders alphabetically (with folders above files)
			folder_list = sorted(folder_list, key=lambda k: k['title'].lower())
			file_list = sorted(file_list, key=lambda k: k['title'].lower())

			# Folder icon
			folder_icon = QtGui.QIcon()
			folder_icon.addPixmap(QtGui.QPixmap(os.path.join('images', 'folder.png')), QtGui.QIcon.Normal, QtGui.QIcon.Off)

			for afile in folder_list:
				item = Qt.QStandardItem(folder_icon, afile['title'])
				item.setCheckable(True)
				self.file_model.appendRow(item)

			for afile in file_list:
				item = Qt.QStandardItem(afile['title'])
				item.setCheckable(True)
				self.file_model.appendRow(item)

			self.file_list.setModel(self.file_model)

	def chooseAuth(self):
		self.initUI('add_account')

	def setStatus(self, text):
		ts = time.time()
		timef = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
		self.status_msg.insertPlainText( timef + ': ' + text + '\n' )

		# Scroll to bottom
		self.status_msg.moveCursor(QtGui.QTextCursor.End)

	def delete_layout(self, the_layout):
		for i in reversed(range(the_layout.count())): 
			the_layout.itemAt(i).widget().setParent(None)

class Auth():
	def __init__(self):
		self.clientId = '285474703712-3leti7pt2o7c683l1260itjv3a0akt6q.apps.googleusercontent.com'
		self.clientSecret = 'bW-MQcRaVzPSowyJ6mJz5HDq'
		self.redirectURI = 'urn:ietf:wg:oauth:2.0:oob'
		self.oauthScope = ['https://www.googleapis.com/auth/drive.readonly', 'email', 'profile', 'https://www.googleapis.com/auth/plus.me']

	def login(self):
		self.flow = OAuth2WebServerFlow(self.clientId, self.clientSecret, self.oauthScope, self.redirectURI)
		authorize_url = self.flow.step1_get_authorize_url()
		webbrowser.open(authorize_url)

	def store_auth(self, auth_code):
		auth_code = str(auth_code)
		self.credentials=None
		try:
			self.credentials = self.flow.step2_exchange(auth_code)
		except FlowExchangeError as e:
			print('Authentication has failed: %s' % e)

		# Create an httplib2.Http object and authorize it with our credentials
		self.connect_to_account()

		if 'Account-'+self.person['id'] not in config_file.Config.sections():
			config_file.edit_config_file(reason='save_account', user_id = self.person['id'], user_name=self.about['name'], user_email=self.person['emails'][0]['value'])
			self.status = 'Account successfully added.'
		else:
			self.status = 'Account not added - already connected.'

		# Store credentials
		file_pi = open(os.path.join('userdata' , 'creds_' + self.person['id']), 'w')
		pickle.dump(self.credentials, file_pi)

		# After any edits, we reload the config file
		config_file.__init__()

	def connect_to_account(self):
		# Create an httplib2.Http object and authorize it with our credentials
		http = httplib2.Http()
		http = self.credentials.authorize(http)

		self.drive_service = build('drive', 'v2', http=http)
		self.about = self.drive_service.about().get().execute()

		self.people_service = build('plus', 'v1', http=http)
		self.person = self.people_service.people().get(userId='me').execute()

class DbConfig():
	def __init__(self):
		#Important variables
		self.version = '0.2'

		# Read config file
		self.Config = ConfigParser.ConfigParser()
		self.Config.readfp(open('config.ini','rw'))

		# If no config file, create one
		if len(self.Config.sections()) < 1:
			self.edit_config_file(reason='create')
			self.status = 'Config file created.'

		else:
			self.status = 'Config file loaded.'

	def edit_config_file(self, **kwargs):
		cfgfile = open("config.ini",'w')
		
		if kwargs['reason'] == 'create':
			self.Config.add_section('General')
			self.Config.set('General', 'Version', self.version)

		elif kwargs['reason'] == 'save_account':
			self.Config.add_section('Account-'+kwargs['user_id'])
			self.Config.set('Account-'+kwargs['user_id'], 'user_name', kwargs['user_name'])
			self.Config.set('Account-'+kwargs['user_id'], 'user_email', kwargs['user_email'])

		self.Config.write(cfgfile)
		cfgfile.close()

class PrintOut():
	colors = { 'header': '\033[95m', 'okblue': '\033[94m', 'okgreen': '\033[92m', 'warning': '\033[93m', 'fail': '\033[91m' }
	def __init__(self, message, msgtype=""):
		if msgtype != "":
			print self.colors[msgtype] + message + '\033[0m'
		else:
			print message

def main():
	session = DriveBackup()

if __name__ == "__main__":
    main()