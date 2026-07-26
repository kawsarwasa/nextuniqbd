# MySQL Setup

This project uses MySQL only in development, testing, and production.

## 1. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

## 2. Create The MySQL Database

Create a UTF-8 database and user in MySQL:

```sql
CREATE DATABASE revo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'revo'@'127.0.0.1' IDENTIFIED BY 'change-this-password';
GRANT ALL PRIVILEGES ON revo.* TO 'revo'@'127.0.0.1';
FLUSH PRIVILEGES;
```

## 3. Point Django At MySQL

Set the environment variables before running Django:

```powershell
$env:DB_ENGINE = "mysql"
$env:DB_NAME = "revo"
$env:DB_USER = "revo"
$env:DB_PASSWORD = "change-this-password"
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "3306"
$env:DB_CHARSET = "utf8mb4"
$env:DB_INIT_COMMAND = "SET sql_mode='STRICT_TRANS_TABLES'"
```

## 4. Build The MySQL Schema

```powershell
python manage.py migrate
python manage.py check
```

## 5. Run The Server

```powershell
python manage.py runserver
```
