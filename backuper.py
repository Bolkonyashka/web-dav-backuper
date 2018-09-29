import os
import easywebdavfixed
import json
import hashlib
import time
from threading import Thread, Lock


class Settings:
    def __init__(self):
        self.settings_dict = ""
        self.cloud_catalog = "/backuper_files"
        self.exists_directories = ''
        self.files_hash = ''
        self.backup_interval = ''
        self.backups_to_cleaning = ''
        self.backup_catalogs = []
        self.backup_mode = False
        self.console_mode = False
        self.lock = Lock()

    def read_settings(self):
        with self.lock:
            with open("settings.json", "r") as file:
                settings_json = file.read()
                self.settings_dict = json.loads(settings_json)
                file.close()
        self.exists_directories = self.settings_dict["existsDirectories"]
        self.files_hash = self.settings_dict["filesHash"]
        self.backup_interval = self.settings_dict["backupInterval"]
        self.backups_to_cleaning = self.settings_dict["backupsCountToCleaning"]
        self.backup_catalogs = self.settings_dict["catalogs"]

    def write_settings(self):
        with self.lock:
            with open("settings.json", "w") as file:
                file.write(json.dumps(self.settings_dict))
                file.close()

    def set_backup_interval(self, inter):
        self.settings_dict["backupInterval"] = inter
        self.backup_interval = inter

    def set_backups_to_cleaning(self, count):
        self.settings_dict["backupsCountToCleaning"] = count
        self.backups_to_cleaning = count

    def set_auth(self, login, passw):
        self.settings_dict["login"] = login
        self.settings_dict["pass"] = passw

    def add_backup_catalog(self, new_path):
        self.backup_catalogs.append(new_path)

    def del_backup_catalog(self, del_path):
        self.backup_catalogs.remove(del_path)

    def conf_cleaning(self):
        self.exists_directories = []
        self.settings_dict["existsDirectories"] = []
        self.files_hash = []
        self.settings_dict["filesHash"] = []


class Backuper(Thread):
    def __init__(self, sett):
        Thread.__init__(self)
        self.settings = sett
        self.webdav_client = easywebdavfixed.Client(protocol='https', host=self.settings.settings_dict["host"],
                                                port=self.settings.settings_dict["port"],
                                                username=self.settings.settings_dict["login"],
                                                password=self.settings.settings_dict["pass"])
        self.main_catalog = ""

    def get_hash_md5(self, filename):
        with open(filename, 'rb') as f:
            m = hashlib.md5()
            while True:
                data = f.read(8192)
                if not data:
                    break
                m.update(data)
            return m.hexdigest()

    def run(self):
        self.get_started()

    def get_started(self):
        self.settings.backup_mode = True
        self.cleaning()
        self.settings.backup_mode = False
        counter = 0
        while True:
            while self.settings.console_mode:  # Ожидание завершения действий с консолью
                pass
            self.settings.backup_mode = True  # Заглушка для консоли
            if counter >= self.settings.backups_to_cleaning:
                counter = 0
                self.cleaning()
            self.settings.read_settings()
            self.do_backup()
            self.settings.write_settings()
            self.settings.backup_mode = False
            counter += 1
            time.sleep(self.settings.backup_interval)

    def get_list_for_backup(self, backup_path):
        backup_list = []
        for file in os.listdir(backup_path):
            path = os.path.join(backup_path, file)
            if not os.path.isdir(path):
                backup_list.append(path.replace(self.main_catalog + '\\', ''))
            else:
                backup_list += self.get_list_for_backup(path)
        return backup_list

    def check_hash_list_and_update(self, file_path):
        file_hash = self.get_hash_md5(file_path)
        for file in self.settings.files_hash:
            if file["filePath"] == file_path:
                if file["hash"] == file_hash:
                    return False
                else:
                    file["hash"] = file_hash
                    return True
        self.settings.files_hash.append({"filePath": file_path, "hash": file_hash})
        return True

    def check_cloud_dirs(self, cloud_path):
        cloud_path_splitted = cloud_path.split('/')
        counter = 1  # 0 - пустая строка, 1 - каталог бекапера
        cloud_path_part = ''
        while counter < len(cloud_path_splitted) - 1:
            cloud_path_part = cloud_path_part + '/' + cloud_path_splitted[counter]
            if cloud_path_part not in self.settings.exists_directories:  # проверка существования директории в облаке
                self.webdav_client.mkdir(cloud_path_part)
                self.settings.exists_directories.append(cloud_path_part)
            counter += 1

    def form_cloud_path(self, file_path, dir_name):
        file_path = file_path.replace('\\', '/')
        cloud_path = self.settings.cloud_catalog + '/' + dir_name + '/' + file_path
        return cloud_path


    def do_backup(self):
        print("Backup started")
        for catalog in self.settings.backup_catalogs:
            catalog = os.path.normpath(catalog)
            if not os.path.isdir(catalog):
                self.settings.backup_catalogs.remove(catalog)
                continue
            self.main_catalog = catalog
            list_for_backup = self.get_list_for_backup(catalog)
            dir_name = catalog.split('\\')
            dir_name = dir_name[len(dir_name) - 1]  # имя директории, которую бекапим
            for file_path in list_for_backup:
                full_file_path = os.path.join(catalog, file_path)
                if self.check_hash_list_and_update(full_file_path):
                    cloud_path = self.form_cloud_path(file_path, dir_name)
                    self.check_cloud_dirs(cloud_path)
                    print("* backuping " + cloud_path)
                    self.webdav_client.upload(full_file_path, cloud_path)
                    print("*** done")
        print("Backup completed")

    def cleaning(self):
        print("Cleaning in action")
        self.webdav_client.delete(self.settings.cloud_catalog)
        self.settings.conf_cleaning()
        self.settings.write_settings()
        print("Cleaning completed")


class ConsoleInterface(Thread):
    def __init__(self, sett):
        Thread.__init__(self)
        self.settings = sett
        self.command_dict = {"conf": self.change_console_mode, "chinterval": self.change_backup_interval,
                             "exit": self.change_console_mode, "chbtc": self.change_backups_to_cleaning,
                             "chauth": self.change_auth, "adddir": self.add_directory, "deldir": self.del_directory}

    def run(self):
        self.input_action()

    def del_directory(self):
        print("* Enter the directory path to remove:")
        del_path = input()
        if del_path not in self.settings.backup_catalogs:
            print("** This path is not exist in backup catalogs list.")
        else:
            self.settings.del_backup_catalog(del_path)
            self.settings.write_settings()
            print("*** The directory path is removed.")

    def add_directory(self):
        print("* Enter the new directory for backup path:")
        new_path = os.path.normpath(input())
        if not os.path.isdir(new_path):
            print("** Path is incorrect or it is not a directory!")
        elif new_path in self.settings.backup_catalogs:
            print("** This path already exists in list for backup.")
        else:
            self.settings.add_backup_catalog(new_path)
            self.settings.write_settings()
            print("*** The new directory for backup path is saved.")


    def change_auth(self):
        new_login = ""
        new_pass = ""
        while len(new_login) < 3:
            print("* Enter the login (min a 3 characters):")
            new_login = input()
        while len(new_pass) < 3:
            print("* Enter the password (min a 3 characters):")
            new_pass = input()
        self.settings.set_auth(new_login, new_pass)
        self.settings.write_settings()
        print("*** The new auth data is saved.")


    def change_backups_to_cleaning(self):
        print("* Enter the number of backups after which the disk will be cleaned up:")
        while True:
            new_count = input()
            try:
                new_count = int(new_count)
            except ValueError:
                print("** Not a number")
                continue
            else:
                self.settings.backups_to_cleaning = new_count
                self.settings.write_settings()
                print("*** The new value is saved.")
                break

    def change_backup_interval(self):
        print("* Enter the new interval (in sec):")
        while True:
            new_interval = input()
            try:
                new_interval = int(new_interval)
            except ValueError:
                print("** Not a number")
                continue
            else:
                self.settings.set_backup_interval(new_interval)
                self.settings.write_settings()
                print("*** The new interval is saved. It will take effect after the next backup.")
                break

    def change_console_mode(self):
        self.settings.console_mode = not self.settings.console_mode  # Заглушка для бекапера
        if self.settings.console_mode:
            print("Configure mode is activated")
        else:
            print("Configure mode is deactivated")

    def input_action(self):
        while True:
            command = input()
            if not self.settings.backup_mode:
                if command not in self.command_dict.keys():
                    print("Unknown command")
                elif not self.settings.console_mode and command != "conf":
                    print("Enter the 'conf' command to change the configuration")
                else:
                    self.command_dict[command]()
            else:
                print("(Blocked) Backup in action. Wait for the backup to complete and enter the command again!")
            self.settings.console_in_action = False


if __name__ == "__main__":
    settings = Settings()
    settings.read_settings()
    backup_client = Backuper(settings)
    console_interface = ConsoleInterface(settings)
    backup_client.start()
    console_interface.start()
