import argparse
import requests
import sys
import os
import easywebdav
import json
import hashlib


class Backuper:
    def __init__(self):
        self.settings = ""
        self.cloud_catalog = "/backuper_files"
        self.read_settings()
        self.exists_directories = self.settings["existsDirectories"]
        self.files_hash = self.settings["filesHash"]
        self.backup_interval = self.settings["backupInterval"]
        self.cleaning_interval = self.settings["cleaningInterval"]
        self.last_backup = self.settings["lastBackup"]
        self.last_cleaning = self.settings["lastCleaning"]
        self.backup_catalog = os.path.normpath(self.settings["catalog"])
        self.webdav_client = easywebdav.connect(protocol='https', host=self.settings["host"],
                                                port=self.settings["port"], username=self.settings["login"],
                                                password=self.settings["pass"])

    def read_settings(self):
        with open("settings.json", "r") as file:
            settings_json = file.read()
            self.settings = json.loads(settings_json)
            file.close()

    def write_settings(self):
        with open("settings.json", "w") as file:
            file.write(json.dumps(self.settings))
            file.close()

    def get_hash_md5(self, filename):
        with open(filename, 'rb') as f:
            m = hashlib.md5()
            while True:
                data = f.read(8192)
                if not data:
                    break
                m.update(data)
            return m.hexdigest()

    def get_started(self):
        self.webdav_client.mkdir("Ziri")

    def get_list_for_backup(self, backup_path):
        backup_list = []
        for file in os.listdir(backup_path):
            path = os.path.join(backup_path, file)
            if not os.path.isdir(path):
                backup_list.append(path.replace(self.backup_catalog + '\\', ''))
            else:
                backup_list += self.get_list_for_backup(path)
        return backup_list

    def check_hash_list_and_update(self, file_path):
        file_hash = self.get_hash_md5(file_path)
        for file in self.files_hash:
            if file["filePath"] == file_path:
                if file["hash"] == file_hash:
                    return False
                else:
                    file["hash"] = file_hash
                    return True
        self.files_hash.append({"filePath": file_path, "hash": file_hash})
        return True

    def do_backup(self):
        print("Backup started")
        list_for_backup = self.get_list_for_backup(self.backup_catalog)
        for file_path in list_for_backup:
            full_file_path = os.path.join(self.backup_catalog, file_path)
            #delete unexisted
            if self.check_hash_list_and_update(full_file_path):
                file_path_splitted = file_path.split('\\')
                #print(file_path_splitted)
                filename = file_path_splitted[len(file_path_splitted) - 1]
                cloud_path = self.cloud_catalog
                counter = 0
                while counter < len(file_path_splitted) - 1:
                    cloud_path = cloud_path + '/' + file_path_splitted[counter]
                    if cloud_path not in self.exists_directories:
                        self.webdav_client.mkdir(cloud_path)
                        self.exists_directories.append(cloud_path)
                    counter += 1
                cloud_path += '/' + filename

                print("* backuping " + cloud_path)
                self.webdav_client.upload(full_file_path, cloud_path)
                print("*** done")
        #print(self.settings["existsDirectories"])
        #print(self.settings["filesHash"])
        print("Backup completed")
        self.write_settings()


if __name__ == "__main__":
    backup_client = Backuper()
    backup_client.do_backup()
    #backup_client.get_started()
