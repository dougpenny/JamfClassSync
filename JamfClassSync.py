#
# JamfClassSync.py
#
# Copyright (c) 2022 Doug Penny
# Licensed under MIT
#
# See LICENSE.md for license information
#
# SPDX-License-Identifier: MIT
#

import csv
import logging
import re
import time

from collections import Counter
from typing import Dict, List

import tomllib

from pyjamfpro import jamfpro


##
## Read values from configuration file
##
with open("jamf_class_sync_config.toml", mode="rb") as config_file:
    config = tomllib.load(config_file)

def build_cart_classes() -> Dict:
    """
    Build a set of cart-based classes. These classes contain generic
    user accounts, already created in Jamf. This type of class is useful
    when iPads are not assigned to individual students.

    Returns:
        A dictionary of classes ready to be created in Jamf.
    """
    class_list = {}
    cart_classes = config.get('cart_classes')
    if cart_classes:
        for cart in cart_classes.keys():
            cart_class = cart_classes[cart]
            students = []
            for i in range(1, cart_class['size']+1):
                students.append(cart + "-user%02d" % i)
            class_list[cart_class['class_name']] = {
                "name": cart_class['class_name'],
                "description": f"The {cart} iPad cart class",
                "students": students,
                "teachers": [cart_class['teacher']]
            }
    return class_list

def build_powerschool_classes() -> Dict:
    """
    Build classes based on lists of PowerSchool export files.

    Returns:
        A dictionary of classes ready to be created in Jamf.
    """
    powerschool_classes = {}
    if config.get('upper_school_file_paths'):
        for file_path in config['upper_school_file_paths']:
            classes = process_upper_school(file_path)
            powerschool_classes.update(classes)
    if config.get('lower_school_file_paths'):
        for file_path in config['lower_school_file_paths']:
            classes = process_lower_school(file_path)
            powerschool_classes.update(classes)
    return powerschool_classes

def classesDoNotMatch(powerschool_class: Dict, jamf_class: Dict) -> bool:
    """
    Compare two class dictionaries to see if they are the same.

    Args:
        powerschool_class (Dict):
            Class created from the PowerSchool export files
        jamf_class (Dict):
            Existing class retrieved directly from Jamf

    Returns:
        True if the class DO NOT match, otherwise False if the classes match.
    """
    if powerschool_class.get('name', False) != jamf_class.get('name', False):
        return True
    if powerschool_class.get('description', False) != jamf_class.get('description', False):
        return True
    if Counter(powerschool_class.get('students', ['student-a'])) != Counter(jamf_class.get('students', ['student-b'])):
        return True
    if Counter(powerschool_class.get('teachers', ['teacher-a'])) != Counter(jamf_class.get('teachers', ['teacher-b'])):
        return True
    return False

def ignore_course(course: str) -> bool:
    """
    Check to see if a course number should be ignored.

    Args:
        course (str):
            Course number to check

    Returns:
        True if the course should be ignored, otherwise False.
    """
    if course in config['ignored_courses']['number']:
        return True
    pre_post_list = re.findall("([A-Z]+)+", course)
    if pre_post_list[0] in config['ignored_courses']['prefix']:
        return True
    if len(pre_post_list) == 2:
        if pre_post_list in config['ignored_courses']['suffix']:
            return True
    return False

def process_lower_school(file_path: str) -> Dict:
    """
    Build a set of lower school classes based on data from
    a PowerSchool export file and the associated config.toml
    file. This type of class is useful when the students
    move from one teacher to another throughout the day, but
    stay together as a group.

    Args:
        file_path (str):
            Path and name of PowerSchool export file to use

    Returns:
        A dictionary of classes ready to be created in Jamf.
    """
    start = time.time()
    class_list = {}
    school_id = ""
    with open(file_path, 'r') as csvfile:
        enrollments = csv.reader(csvfile, delimiter='\t')
        for record in enrollments:
            if record[0] in config['lower_school_class_names'].keys():
                class_name = config['lower_school_class_names'][record[0]][record[7]]
                existing_class = class_list.get(class_name)
                if existing_class:
                    students = existing_class['students']
                    if record[6] not in students:
                        students.append(record[6])
                        existing_class['students'] = students
                    class_list[class_name] = existing_class
                else:
                    new_class = {
                        "id": record[3],
                        "name": class_name,
                        "description": f"{class_name} class",
                        "students": [record[6]],
                        "teachers": config['lower_school_teachers'][record[0]]
                    }
                    class_list[class_name] = new_class
            school_id = record[8]
    end = time.time()
    logging.info(f"{len(class_list)} classes found in PowerSchool for school number {school_id} in {(end - start):.4f} seconds")
    return class_list

def process_upper_school(file_path: str) -> Dict:
    """
    Build a set of upper school classes based on data from
    a PowerSchool export file and the associated config.toml
    file. This type of class represents a traditional class
    (section in PowerSchool) that meets during a specifc time
    slot or period.

    Args:
        file_path (str):
            Path and name of PowerSchool export file to use

    Returns:
        A dictionary of classes ready to be created in Jamf.
    """
    start = time.time()
    class_list = {}
    school_id = ""
    with open(file_path, 'r') as csvfile:
        enrollments = csv.reader(csvfile, delimiter='\t')
        for record in enrollments:
            if not ignore_course(record[0]):
                period = config['period_by_school_number'][record[8]][record[4][:1]]
                class_name = f"{period} - {record[1]} ({record[0]}.{record[2]})"
                existing_class = class_list.get(class_name)
                if existing_class:
                    students = existing_class['students']
                    if record[6] not in students:
                        students.append(record[6])
                        existing_class['students'] = students
                    teachers = existing_class['teachers']
                    if record[7] not in teachers:
                        teachers.append(record[7])
                        existing_class['teachers'] = teachers
                    class_list[class_name] = existing_class
                else:
                    new_class = {
                        "id": record[3],
                        "name": class_name,
                        "description": f"{record[1]} meeting during {period} period in room {record[5]}",
                        "students": [record[6]],
                        "teachers": [record[7]]
                    }
                    class_list[class_name] = new_class
            school_id = record[8]
    end = time.time()
    logging.info(f"{len(class_list)} classes found in PowerSchool for school number {school_id} in {(end - start):.4f} seconds")
    return class_list


def main():
    logging.basicConfig(level=logging.INFO, filename=config['log_file_path'], format='%(asctime)s - %(levelname)s: %(message)s', datefmt='%d-%b-%y %H:%M:%S')
    logging.info('** Start log for JamfClassSync.py **')
    start = time.time()
    
    #
    # Build a dictionary of classes based on the nightly exports from PowerSchool
    #
    current_classes: Dict = build_powerschool_classes()

    #
    # Build any cart-based classes and add them to the dictionary of current classes
    #
    cart_classes = build_cart_classes()
    current_classes.update(cart_classes)

    #
    # Instantiate the PyJamfPro client for communicating with the Jamf server
    #
    client = jamfpro.Client(config['jamf_domain'], config['jamf_username'], config['jamf_password'])
    
    #
    # Delete any classes currently in Jamf, but no longer in PowerSchool
    #
    logging.info("Checking for classes in Jamf, but no longer in PowerSchool")
    start_delete = time.time()
    jamf_classes: List = client.classic_classes()
    deleted = 0
    delete_retries = []
    delete_failed = []
    indexed_jamf_classes = {}
    for jamf_class in jamf_classes:
        class_name = jamf_class.get('name', False)
        if class_name:
            found = current_classes.get(class_name, False)
            if not found:
                success = client.classic_delete_class_with_name(class_name)
                if success:
                    deleted = deleted + 1
                else:
                    delete_retries.append(class_name)
                    logging.info(f"Tried to delete {class_name} from Jamf, but was unsuccessful. Will try again.")
            else:
                indexed_jamf_classes[class_name] = jamf_class
    if len(delete_retries) > 0:
        for delete_class in delete_retries:
            success = client.classic_delete_class_with_name(delete_class)
            if success:
                deleted = deleted + 1
            else:
                delete_failed.append(delete_class)
                logging.warning(f"Tried to delete {delete_class} from Jamf, but was unsuccessful. This class may need to be deleted manually.")
    end_delete = time.time()
    logging.info(f"Deleted {deleted} class(es) found in Jamf, but no longer in PowerSchool in {(end_delete - start_delete):.4f} seconds")

    #
    # First compare the PowerSchool class to the Jamf class and update the class if
    # there are any differences. If the class is not currently in Jamf, create the class.
    #
    logging.info("Creating or updating classes in Jamf")
    start_update = time.time()
    added = 0
    add_retries = []
    add_failed = []
    updated = 0
    update_retries = []
    update_failed = []
    for class_name in current_classes.keys():
        jamf_class = client.classic_class_with_name(class_name)
        if jamf_class:
            if classesDoNotMatch(current_classes[class_name], jamf_class):
                class_id = client.classic_update_class_with_name(class_name, current_classes[class_name])
                if class_id:
                    updated = updated + 1
                else:
                    update_retries.append(current_classes[class_name])
                    logging.info(f"Tried to update {class_name} in Jamf, but was unsuccessful. Will try again.")
        else:
            class_id = client.classic_new_class(current_classes[class_name])
            if class_id:
                added = added + 1
            else:
                add_retries.append(current_classes[class_name])
                logging.info(f"Tried to create {class_name} in Jamf, but was unsuccessful. Will try again.")
    if len(update_retries) > 0:
        for update_class in update_retries:
            class_id = client.classic_update_class_with_name(update_class['name'], update_class)
            if class_id:
                updated = updated + 1
            else:
                update_failed.append(update_class)
                logging.warning(f"Tried to update {update_class['name']} in Jamf, but was unsuccessful. This class may need to be updated manually.")
    if len(add_retries) > 0:
        for add_class in add_retries:
            class_id = client.classic_new_class(add_class)
            if class_id:
                added = added + 1
            else:
                add_failed.append(add_class)
                logging.warning(f"Tried to create {add_class['name']} in Jamf, but was unsuccessful. Will try again. This class may need to be added manually.")
    end_update = time.time()
    logging.info(f"Created {added} new class(es) and updated {updated} existing class(es) in Jamf in {(end_update - start_update):.4f} seconds\n")

    end = time.time()
    if len(delete_failed) > 0:
        logging.warn("The following classes were not removed from Jamf, but are no longer in PowerSchool. You may need to manually delete these classes.")
        for delete_class in delete_failed:
            logging.warn(f"\t** {delete_class}")
    if len(update_failed) > 0:
        logging.warn("The following classes failed to update in Jamf. You may need to manually update these classes.")
        for update_class in update_failed:
            logging.warn(f"\t** {update_class['name']}")
    if len(add_failed) > 0:
        logging.warn("The following classes failed to be created in Jamf. You may need to manually add these classes.")
        for add_class in add_failed:
            logging.warn(f"\t** {add_class['name']}")
    
    logging.info(f"Total elased time was {(end - start):.4f} seconds")
    logging.info('** End log for JamfClassSync.py **\n')


if __name__ == '__main__':
    main()
