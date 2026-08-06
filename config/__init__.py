import pymysql


# Django 6 checks the MySQLdb compatibility version. PyMySQL exposes its
# historical compatibility tuple by default, so declare the supported API
# level before registering it as MySQLdb.
pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.install_as_MySQLdb()
