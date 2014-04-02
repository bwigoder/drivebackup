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
import threading

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
			self.status_msg = QtGui.QTextEdit(w)
			self.status_msg.setReadOnly(True)
			self.status_msg.setMaximumHeight(90)
			self.setStatus("DriveBackup Initiated.")

			# Add Account Button
			self.add_account_btn = Qt.QPushButton("Add Account", w)
			self.add_account_btn.setFixedWidth(140)
			app.connect(self.add_account_btn, Qt.SIGNAL("clicked()"), self.chooseAuth)

			# Place objects on screen
			self.master = QtGui.QVBoxLayout()
			self.master.addWidget(self.welcome_msg)
			self.action_bar = QtGui.QGridLayout()
			self.action_bar_acc = QtGui.QHBoxLayout()
			self.progress_bar_row = QtGui.QGridLayout()

			# List accounts
			self.updateAccountsList()
			self.action_bar.addWidget(self.add_account_btn, 0, 1)

			# Account info area
			self.select_files_msg = QtGui.QLabel()
			self.select_files_msg.setText('Select files + folders for automated backup:')

			self.acc_info = QtGui.QGridLayout()
			self.file_list = Qt.QListView(self)
			self.file_list.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
			self.file_list.setMaximumSize(QtCore.QSize(16777215, 150))
			self.file_list.setAlternatingRowColors(True)
			self.file_model = Qt.QStandardItemModel(self.file_list)
			self.file_model.itemChanged.connect(self.onFilesChanged)

			# Account action bar
			self.select_toggle_btn = Qt.QPushButton("Select All/None", w)
			self.select_toggle_btn.setEnabled(False)
			self.select_toggle_btn.setFixedWidth(140)
			app.connect(self.select_toggle_btn, Qt.SIGNAL("clicked()"), self.selectToggle)

			self.backup_btn = Qt.QPushButton("Backup", w)
			self.backup_btn.setEnabled(False)
			app.connect(self.backup_btn, Qt.SIGNAL("clicked()"), self.backupClicked)

			self.del_acc_btn = Qt.QPushButton("Remove Account", w)
			self.del_acc_btn.setEnabled(False)
			self.del_acc_btn.setFixedWidth(140)
			self.del_acc_btn.setAutoFillBackground(True)
			app.connect(self.del_acc_btn, Qt.SIGNAL("clicked()"), self.delAccount)

			self.action_bar_acc.addWidget(self.select_toggle_btn)
			self.action_bar_acc.addWidget(self.backup_btn)
			self.action_bar_acc.addWidget(self.del_acc_btn)

			# Progress bar
			self.progress_bar = QtGui.QProgressBar(self)
			self.progress_bar.setGeometry(30, 40, 200, 25)
			self.progress_bar.hide()
			self.progress_bar_row.addWidget(self.progress_bar, 0, 1)

			# Folder icon
			self.folder_icon = QtGui.QIcon()
			self.folder_icon.addPixmap(QtGui.QPixmap(os.path.join('images', 'folder.png')), QtGui.QIcon.Normal, QtGui.QIcon.Off)

			self.acc_info.addWidget(self.select_files_msg)
			self.acc_info.addWidget(self.file_list)

			self.status_area = QtGui.QGridLayout()
			self.status_area.addWidget(self.status_msg, 1, 0)

			self.master.addLayout(self.action_bar)
			self.master.addLayout(self.acc_info)
			self.master.addLayout(self.action_bar_acc)
			self.master.addLayout(self.progress_bar_row)
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
		self.accounts_list.addItem('Please select an account or add a new one.', '')

		# Add items from config
		for i in config_file.Config.sections():
			if i[:7] == 'Account':
				# Check a config file exists
				if os.path.isfile(os.path.join('userdata' , i[8:] + '_creds')):
					self.accounts_list.addItem(config_file.Config.get(i, 'user_email') +  ' (' + config_file.Config.get(i, 'user_name') + ')', i[8:])
				else:
					self.setStatus ('Userdata file for account ' + config_file.Config.get(i, 'user_email') + ' is missing!')
					config_file.Config.remove_section(i)
					self.setStatus ('Removed account ' + config_file.Config.get(i, 'user_email') + ' from config.')

		# Remove widget + re-add it
		self.action_bar.removeWidget(self.accounts_list)
		self.action_bar.addWidget(self.accounts_list, 0, 0)

		# Set a signal to reload files on change
		self.connect(self.accounts_list, QtCore.SIGNAL("currentIndexChanged(const QString&)"), self.accountChanged)

		# Select the account just added using most recent authorised session
		if hasattr(self, 'session'):
			index=self.accounts_list.findData(self.session.person['id'])
			self.accounts_list.setCurrentIndex(index)

	def accountChanged(self):
		self.selected_item_in_list = self.accounts_list.currentIndex()

		# Update file list in background
		self.setStatus('Please wait - loading...', 'waiting')
		updateThread = threading.Thread(target=self.updateFileList)
		updateThread.start()

	def updateButtons(self):
		# Enable/disable buttons
		if self.selected_item_in_list != 0:
			self.select_toggle_btn.setEnabled(True)
			self.del_acc_btn.setEnabled(True)
		else:
			self.select_toggle_btn.setEnabled(False)
			self.del_acc_btn.setEnabled(False)

		self.backup_btn.setEnabled(False)
		if self.countChecked() > 0:
			self.backup_btn.setEnabled(True)

	def updateFileList(self):
		# Get selected account/user ID
		self.selected_user_id = str(self.accounts_list.itemData(self.selected_item_in_list).toString())
		
		# Remove all files in list
		self.file_model.clear()

		# Connect to this account, if there is an account
		if len(self.selected_user_id) > 0:
			filehandler = open(os.path.join('userdata' , self.selected_user_id + '_creds'), 'r')

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

			# Create a combined list (shallow copy)
			self.all_files_and_folders = folder_list + file_list

			for afile in folder_list:
				item = Qt.QStandardItem(self.folder_icon, afile['title'])
				item.setCheckable(True)
				self.file_model.appendRow(item)

			for afile in file_list:
				item = Qt.QStandardItem(afile['title'])
				item.setCheckable(True)
				self.file_model.appendRow(item)

			self.file_list.setModel(self.file_model)

			self.setStatus('File list loaded.','success')

		else:
			self.setStatus('Please select an account.','warning')			

		# Update number of files + folders
		self.total_files_and_folders = self.file_model.rowCount()

		# Now update buttons
		self.updateButtons()

	def backupClicked(self):
		# Files to be backup up
		items_for_backup = self.getChecked()

		sel_backup_location = ''

		# Decide where to store backups
		if config_file.Config.has_option('Account-' + self.selected_user_id, 'backup_location') != True:
			ret = QtGui.QMessageBox.information(self, "First time backup", "You will now be prompted to select a location to store the backed up files.", QtGui.QMessageBox.Ok, QtGui.QMessageBox.Cancel)
			if ret == QtGui.QMessageBox.Ok:
				sel_backup_location = str(QtGui.QFileDialog.getExistingDirectory(None, "Select Backup Directory",'backups',QtGui.QFileDialog.ShowDirsOnly))

		else:
			sel_backup_location = config_file.Config.get('Account-' + self.selected_user_id, 'backup_location')

		# Ensure that we have a backup location
		if sel_backup_location != '':

			# Workaround 'untitled bug' on OSX
			if sel_backup_location[-8:] == 'untitled':
				sel_backup_location = sel_backup_location[:-8]

			# Store it in config file
			config_file.edit_config_file(reason='store_backup_location', user_id = self.selected_user_id, backup_location = sel_backup_location)

			# Check that we have write access
			if os.access(sel_backup_location, os.W_OK) != True:
				self.setStatus('No write access to backup location: ' + sel_backup_location,'error')
			else:
				# Begin backup
				self.beginBackup(sel_backup_location, items_for_backup)

	def beginBackup(self, sel_backup_location, items_for_backup):
		# Disable UI
		self.accountUI(False)

		# Show progress bar
		self.progress_bar.show()

		# Update status
		self.setStatus('Backup started...','waiting')

		total_items = len(items_for_backup)

		# Actual backup location
		full_backup_location = os.path.join(sel_backup_location, self.selected_user_id)

		# Create this folder if it doesn't exist
		if not os.path.exists(full_backup_location):
			os.makedirs(full_backup_location)

		# Backup loop
		i = 0;
		for item in items_for_backup:
			# Force GUI to update
			app.processEvents()

			# Backup files
			if item['mimeType'] == 'application/vnd.google-apps.folder':
				pass

			else:
				pass

			# Update progress bar
			self.progress_bar.setProperty("value", ( float(i) / total_items * 100 ) )
			i += 1

		# -- Backup complete --
		# Remove progress bar
		self.progress_bar.hide()
		self.progress_bar.setProperty("value", 0)

		# Update status
		self.setStatus('Backup complete!','success')

		# Enable UI
		self.accountUI(True)

	def onFilesChanged(self):
		self.updateButtons()

	def chooseAuth(self):
		self.initUI('add_account')

	def delAccount(self):
		ret = QtGui.QMessageBox.information(self, "Remove Account", "This feature is coming soon.", QtGui.QMessageBox.Ok, QtGui.QMessageBox.Cancel)

	def accountUI(self, toggle):
		# Toggle account buttons
		buttons = [self.select_toggle_btn, self.backup_btn, self.del_acc_btn, self.add_account_btn, self.accounts_list]

		for b in buttons:
			b.setEnabled(toggle)

		# Prevent checkboxes from being deselected/selected

	def setStatus(self, text, msgtype=''):
		# Scroll to bottom
		self.status_msg.moveCursor(QtGui.QTextCursor.End)
		self.status_msg.ensureCursorVisible()

		color = self.mapColor(msgtype)
		ts = time.time()
		timef = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
		self.status_msg.setTextColor(QtGui.QColor(color))
		self.status_msg.insertPlainText( timef + ': ' + text + '\n' )

	def delete_layout(self, the_layout):
		for i in reversed(range(the_layout.count())): 
			the_layout.itemAt(i).widget().setParent(None)

	def mapColor(self, color):
		colors = {
			'':			'#000000',
			'error':	'#FF0000',
			'warning':	'#FF6600',
			'success':	'#00AF33',
			'waiting':	'#6699FF'
		}
		return colors[color]

	def selectToggle(self):
		# Decide how to toggle
		newstate = 0
		if self.countChecked() < self.total_files_and_folders:
			newstate = 2

		# Iterate through each file, to change the checked state
		for i in range(self.total_files_and_folders):
			self.file_model.item(i).setCheckState(newstate)

	def countChecked(self):
		total_checked = 0
		for i in range(self.total_files_and_folders):
			if self.file_model.item(i).checkState() == 2:
				total_checked += 1
		return total_checked

	def getChecked(self):
		selected_for_backup = []
		for i in range(self.total_files_and_folders):
			if self.file_model.item(i).checkState() == 2:
				selected_for_backup.append(self.all_files_and_folders[i])
		return selected_for_backup

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
		file_pi = open(os.path.join('userdata' , self.person['id'] + '_creds'), 'w')
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
		self.Config.read('config.ini')

		# If no config file, create one
		if len(self.Config.sections()) < 1:
			self.edit_config_file(reason='create')
			self.status = 'Config file created.'

		else:
			self.status = 'Config file loaded.'

		self.Config.readfp(open('config.ini','rw'))

	def edit_config_file(self, **kwargs):
		cfgfile = open("config.ini",'w')
		
		if kwargs['reason'] == 'create':
			self.Config.add_section('General')
			self.Config.set('General', 'Version', self.version)

		elif kwargs['reason'] == 'save_account':
			self.Config.add_section('Account-'+kwargs['user_id'])
			self.Config.set('Account-'+kwargs['user_id'], 'user_name', kwargs['user_name'])
			self.Config.set('Account-'+kwargs['user_id'], 'user_email', kwargs['user_email'])

		elif kwargs['reason'] == 'store_backup_location':
			self.Config.set('Account-'+kwargs['user_id'], 'backup_location', kwargs['backup_location'])

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