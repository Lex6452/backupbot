# 🤖 Database Backup Bot

[🇷🇺 Русская версия](README-RU.md)

A powerful Telegram bot for automated database backups with SSH support and web interface.

## ✨ Features

- **🔄 Multi-Database Support**: PostgreSQL, MySQL, SQLite, MongoDB
- **🔐 SSH Tunneling**: Secure connections to remote servers
- **📅 Automated Backups**: Scheduled daily backups at 2:00 AM
- **📱 Telegram Interface**: Full control via Telegram messages
- **📊 Backup Management**: Download, organize, and manage backups
- **🔒 Security**: Admin-only access with proper authentication
- **📈 Monitoring**: Connection testing and status monitoring
- **🌐 SSH Server Management**: Direct server management via SSH
- **📦 Backup Transfer**: Upload backups to remote backup servers

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Telegram Bot Token
- Database credentials for your databases

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Lex6452/backupbot.git
   cd backupbot
   ```

2. **Create and activate virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. **Configure .env file**
   ```env
   BOT_TOKEN=your_telegram_bot_token_here
   ADMIN_ID=your_telegram_user_id
   BACKUP_DIR=./backups
   TIMEZONE=Europe/Moscow
   ```

6. **Run the bot**
   ```bash
   python main.py
   ```

## 📋 How to Get Bot Token and Admin ID

### Getting Bot Token

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the bot token (looks like `1234567890:ABCdefGHIjklMNopQRstUVwxyz`)
5. Add it to your `.env` file as `BOT_TOKEN`

### Getting Your Admin ID

1. Open Telegram and search for `@userinfobot`
2. Start the bot
3. It will show your user ID
4. Copy the ID and add it to your `.env` file as `ADMIN_ID`

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BOT_TOKEN` | Telegram Bot Token from @BotFather | - | **Yes** |
| `ADMIN_ID` | Your Telegram User ID | - | **Yes** |
| `BACKUP_DIR` | Directory for storing backups | `./backups` | No |
| `TIMEZONE` | Timezone for scheduler | `Europe/Moscow` | No |

### Database Connection Types

#### PostgreSQL
- **Required**: Host, Port, Database, Username, Password
- **Backup Tool**: `pg_dump`
- **Test Command**: `psql --version`

#### MySQL
- **Required**: Host, Port, Database, Username, Password
- **Backup Tool**: `mysqldump`
- **Test Command**: `mysql --version`

#### SQLite
- **Required**: File path
- **Optional**: SSH connection details
- **Backup Method**: File copy or SSH transfer
- **Test Command**: `sqlite3 --version`

#### MongoDB
- **Required**: Host, Port, Database, Username, Password
- **Backup Tool**: `mongodump`
- **Test Command**: `mongodump --version`

## 🗂️ Project Structure

```
backupbot/
├── main.py                 # Main application entry point
├── handlers/               # Telegram handlers
│   ├── admin.py           # Admin commands and menus
│   ├── backup.py          # Backup management
│   ├── ssh_handlers.py    # SSH server management
│   └── snapshot_handlers.py # Backup server management
├── utils/                  # Utility modules
│   ├── db.py              # Database operations
│   ├── scheduler.py       # Automated backup scheduler
│   ├── ssh_client.py      # SSH connection management
│   ├── ssh_utils.py       # SSH utilities and ping
│   ├── backup_transfer.py # Backup file transfer
│   └── connection_test.py # Database connection testing
├── backups/                # Backup storage directory
├── logs/                   # Application logs
└── requirements.txt        # Python dependencies
```

## 🎯 Usage

### Starting the Bot

1. **Start the bot application:**
   ```bash
   python main.py
   ```

2. **Open Telegram and find your bot**
3. **Send `/start` command**
4. **You'll see the main menu with all available options**

### Main Menu Options

- **📊 Connection List** - View and manage all database connections
- **➕ Add Connection** - Add new database connection
- **🔄 Make Backup** - Create manual backup immediately
- **📁 Backup Manager** - Browse, download and manage backup files
- **🔐 SSH** - Manage SSH servers and execute commands
- **⚙️ AutoBackup Settings** - Configure automated backup schedules
- **📋 Backup Logs** - View backup history and status

### Adding a Database Connection

1. Click **"➕ Add Connection"**
2. Select database type:
   - **PostgreSQL** - For PostgreSQL databases
   - **MySQL** - For MySQL/MariaDB databases  
   - **SQLite** - For SQLite database files
   - **MongoDB** - For MongoDB databases

3. **For PostgreSQL/MySQL/MongoDB:**
   - Enter connection name
   - Provide host, port, database name
   - Enter username and password
   - Test connection before saving

4. **For SQLite:**
   - Choose between local file or SSH connection
   - For SSH: Provide SSH credentials and remote file path
   - For local: Provide local file path

### SSH Features

When `SSH_ENABLED=true` in your `.env` file:

- **🔌 Connect** - Establish SSH connection to servers
- **🏓 Ping** - Measure server response time with detailed statistics
- **🔄 Reboot** - Safely reboot remote servers with monitoring
- **📦 Update** - Update system packages with progress tracking
- **💻 Execute** - Run commands in interactive SSH session
- **📁 Browse** - Navigate server file system

### Automated Backups

- **Schedule**: Runs daily at 2:00 AM (configurable)
- **Scope**: Backs up all enabled connections
- **Reporting**: Sends detailed report to admin after completion
- **Logging**: Comprehensive logging of all backup attempts
- **Backup Server**: Optional upload to remote backup servers

## 🔧 Advanced Features

### Backup Management

- **File Browser**: Paginated list of all backup files
- **Direct Download**: Download backups directly in Telegram
- **File Information**: View sizes, dates, and creation times
- **Organization**: Automatic naming with timestamps

### Connection Testing

- **Pre-Save Testing**: Test connections before saving credentials
- **Detailed Reports**: Get database version, size, and status
- **Error Diagnostics**: Clear error messages for troubleshooting
- **SSH Verification**: Test SSH connections and file access

### Security Features

- **Admin-Only Access**: Restricted to configured admin ID
- **Secure Storage**: Encrypted credential storage in database
- **Connection Timeouts**: Prevent hanging connections
- **Input Validation**: Sanitized user inputs
