import os
import easywebdav
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
        self.cleaning_interval = ''
        self.last_backup = ''
        self.last_cleaning = ''
        self.backup_catalog = ''
        self.backup_in_action = False
        self.console_in_action = False

    def read_settings(self):
        with open("settings.json", "r") as file:
            settings_json = file.read()
            self.settings_dict = json.loads(settings_json)
            file.close()
        self.exists_directories = self.settings_dict["existsDirectories"]
        self.files_hash = self.settings_dict["filesHash"]
        self.backup_interval = self.settings_dict["backupInterval"]
        self.cleaning_interval = self.settings_dict["cleaningInterval"]
        self.last_backup = self.settings_dict["lastBackup"]
        self.last_cleaning = self.settings_dict["lastCleaning"]
        self.backup_catalog = os.path.normpath(self.settings_dict["catalog"])

    def write_settings(self):
        with open("settings.json", "w") as file:
            file.write(json.dumps(self.settings_dict))
            file.close()

    def set_backup_interval(self, inter):
        self.settings_dict["backupInterval"] = inter
        self.backup_interval = inter


class Backuper(Thread):
    def __init__(self, sett):
        Thread.__init__(self)
        self.settings = sett
        self.webdav_client = easywebdav.connect(protocol='https', host=self.settings.settings_dict["host"],
                                                port=self.settings.settings_dict["port"],
                                                username=self.settings.settings_dict["login"],
                                                password=self.settings.settings_dict["pass"])

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
        while True:
            time.sleep(self.settings.backup_interval)
            while self.settings.console_in_action:  # Ожидание завершения действий с консолью
                pass
            lock = Lock()
            self.settings.backup_in_action = True  # Заглушка для консоли
            with lock:
                self.settings.read_settings()
                self.do_backup()
                self.settings.write_settings()
            self.settings.backup_in_action = False

    def get_list_for_backup(self, backup_path):
        backup_list = []
        for file in os.listdir(backup_path):
            path = os.path.join(backup_path, file)
            if not os.path.isdir(path):
                backup_list.append(path.replace(self.settings.backup_catalog + '\\', ''))
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

    def do_backup(self):
        print("Backup started")
        list_for_backup = self.get_list_for_backup(self.settings.backup_catalog)
        dir_name = self.settings.backup_catalog.split('\\')
        dir_name = dir_name[len(dir_name) - 1]  # имя директории, которую бекапим
        for file_path in list_for_backup:
            full_file_path = os.path.join(self.settings.backup_catalog, file_path)
            if self.check_hash_list_and_update(full_file_path):
                file_path_splitted = file_path.split('\\')
                filename = file_path_splitted[len(file_path_splitted) - 1]
                file_path_splitted.insert(0, dir_name)  # всегда вставляем имя директории
                cloud_path = self.settings.cloud_catalog
                counter = 0
                while counter < len(file_path_splitted) - 1:
                    cloud_path = cloud_path + '/' + file_path_splitted[counter]
                    if cloud_path not in self.settings.exists_directories:  # проверка существования директории в облаке
                        self.webdav_client.mkdir(cloud_path)
                        self.settings.exists_directories.append(cloud_path)
                    counter += 1
                cloud_path += '/' + filename
                print("* backuping " + cloud_path)
                self.webdav_client.upload(full_file_path, cloud_path)
                print("*** done")
        print("Backup completed")


class ConsoleInterface(Thread):
    def __init__(self, sett):
        Thread.__init__(self)
        self.settings = sett
        self.command_dict = {"chinterval": self.change_backup_interval}

    def run(self):
        self.input_action()

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
                print("** The new interval is saved. It will take effect after the next backup.")
                break

    def input_action(self):
        while True:
            command = input()
            self.settings.console_in_action = True  # Заглушка для бекапера
            if not self.settings.backup_in_action:
                if command not in self.command_dict.keys():
                    print("Unknown command")
                else:
                    lock = Lock()
                    with lock:
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
