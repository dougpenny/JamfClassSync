#
# JamfClassDelete.py
#
# Copyright (c) 2024 Doug Penny
# Licensed under MIT
#
# See LICENSE for license information
#
# SPDX-License-Identifier: MIT
#

import logging
import time

from typing import Dict, List

import tomllib

from pyjamfpro import jamfpro


##
## Read values from configuration file
##
with open("jamf_class_sync_config.toml", mode="rb") as config_file:
    config = tomllib.load(config_file)


def main():
    logging.basicConfig(
        level=logging.INFO,
        filename=config["log_file_path"],
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt="%d-%b-%y %H:%M:%S",
    )
    logging.info("** Start log for JamfClassDelete.py **")
    start = time.time()

    #
    # Instantiate the PyJamfPro client for communicating with the Jamf server
    #
    client = jamfpro.Client(
        config["jamf_domain"], config["jamf_client_id"], config["jamf_client_secret"]
    )

    deleted: int = 0
    delete_retires: List = []
    delete_failed: List = []

    #
    # Fetch all existing classes from Jamf
    #
    existing_classes: List = client.classic_classes()

    #
    # Delete all existing classed from Jamf
    #
    jamf_class: Dict
    for jamf_class in existing_classes:
        class_id: int = jamf_class.get("id", 0)
        success: bool = client.classic_delete_class_with_id(class_id)
        if success:
            deleted = deleted + 1
        else:
            delete_retires.append(class_id)
            logging.info(
                f"Tried to delete class with ID {class_id} from Jamf, but was unsuccessful. Will try again."
            )

    if len(delete_retires) > 0:
        deleted_id: int
        for delete_id in delete_retires:
            success: bool = client.classic_delete_class_with_id(delete_id)
            if success:
                deleted = deleted + 1
            else:
                delete_failed.append(delete_id)
                logging.warning(
                    f"Tried to delete class with ID {delete_id} from Jamf, but was unsuccessful. This class may need to be deleted manually."
                )

    end = time.time()
    logging.info(
        f"Deleted {deleted} class(es) found in Jamf in {(end - start):.4f} seconds."
    )
    logging.info("** End log for JamfClassDelete.py **\n")


if __name__ == "__main__":
    main()
