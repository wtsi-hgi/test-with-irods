import unittest
from abc import ABCMeta

import testwithirods
from testwithirods.models import Metadata
from testwithirods.helpers import SetupHelper, AccessLevel
from testwithirods.irods_contoller import IrodsServerController
from testwithirods.models import IrodsUser
from testwithirods.proxies import ICommandProxyController
from testwithirods.tests._common import IcatTest, create_tests_for_all_irods_setups

_METADATA = Metadata({
    "attribute_1": ["value_1", "value_2"],
    "attribute_2": ["value_3", "value_4"],
    "attribute_3": "value_5"
})
_DATA_OBJECT_NAME = "data-object-name"


class TestSetupHelper(IcatTest, metaclass=ABCMeta):
    """
    Tests for `SetupHelper`.
    """
    def setUp(self):
        self._server_controller = self.ServerController()   # type: IrodsServerController
        self.irods_server = self._server_controller.start_server()

        self._proxy_controller = ICommandProxyController(self.irods_server, self.compatible_baton_image)
        icommands_location = self._proxy_controller.create_proxy_binaries()

        self.setup_helper = SetupHelper(icommands_location)

    def tearDown(self):
        self._server_controller.stop_server(self.irods_server)
        self._proxy_controller.create_proxy_binaries()

    def test_run_icommand(self):
        ils = self.setup_helper.run_icommand(["ils"])
        self.assertTrue(ils.startswith("/"))
        self.assertTrue(ils.endswith(":"))

    def test_create_data_object_with_path_opposed_to_name(self):
        self.assertRaises(ValueError, self.setup_helper.create_data_object, "/test")

    def test_create_data_object(self):
        contents = "Test contents"
        path = self.setup_helper.create_data_object(_DATA_OBJECT_NAME, contents=contents)
        self.setup_helper.run_icommand(["icd", path.rsplit('/', 1)[-1]])
        self.assertIn(_DATA_OBJECT_NAME, self.setup_helper.run_icommand(["ils"]))
        # FIXME: Not testing for contents

    def test_replicate_data_object(self):
        data_object_location = self.setup_helper.create_data_object(_DATA_OBJECT_NAME)
        resource = self.setup_helper.create_replica_storage()
        self.setup_helper.replicate_data_object(data_object_location, resource)

        collection_listing = self.setup_helper.run_icommand(["ils", "-l"])
        self.assertIn("1 %s" % resource.name[0:20], collection_listing)

    def test_create_collection(self):
        collection_name = "collection"
        path = self.setup_helper.create_collection(collection_name)

        self.setup_helper.run_icommand(["icd", path.rsplit('/', 1)[-1]])
        self.assertIn(collection_name, self.setup_helper.run_icommand(["ils"]))

    def test_create_collection_with_collection_path_opposed_to_collection_name(self):
        self.assertRaises(ValueError, self.setup_helper.create_collection, "/test")

    def test_add_metadata_to_data_object(self):
        path = self.setup_helper.create_data_object(_DATA_OBJECT_NAME)

        self.setup_helper.add_metadata_to(path, _METADATA)

        retrieved_metadata = self.setup_helper.run_icommand(["imeta", "ls", "-d", path])
        self._assert_metadata_in_retrieved(_METADATA, retrieved_metadata)

    def test_add_metadata_to_collection(self):
        path = self.setup_helper.create_collection("collection")

        self.setup_helper.add_metadata_to(path, _METADATA)

        retrieved_metadata = self.setup_helper.run_icommand(["imeta", "ls", "-c", path])
        self._assert_metadata_in_retrieved(_METADATA, retrieved_metadata)

    def test_update_checksums(self):
        path = self.setup_helper.create_data_object(_DATA_OBJECT_NAME, "abc")
        resource = self.setup_helper.create_replica_storage()
        self.setup_helper.replicate_data_object(_DATA_OBJECT_NAME, resource)

        expected_checksum = "900150983cd24fb0d6963f7d28e17f72" if self.irods_server.version.major == 3 \
            else "sha2:ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0="

        # Asserting that checksum is not stored before now
        assert expected_checksum not in self.setup_helper.run_icommand(["ils", "-L", path])
        self.setup_helper.update_checksums(path)

        ils = self.setup_helper.run_icommand(["ils", "-L", path])
        self.assertEquals(ils.count(expected_checksum), 2)

    def test_get_checksum(self):
        path = self.setup_helper.create_data_object(_DATA_OBJECT_NAME, "abc")
        expected_checksum = "900150983cd24fb0d6963f7d28e17f72" if self.irods_server.version.major == 3 \
            else "sha2:ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0="
        self.assertEquals(self.setup_helper.get_checksum(path), expected_checksum)

    def test_create_replica_storage(self):
        resource = self.setup_helper.create_replica_storage()
        resource_info = self.setup_helper.run_icommand(["iadmin", "lr", resource.name])
        self.assertIn("resc_name: %s" % resource.name, resource_info)
        self.assertIn("resc_def_path: %s" % resource.location, resource_info)

    def test_create_user_with_existing_username(self):
        existing_user = self.irods_server.users[0]
        self.assertRaises(ValueError, self.setup_helper.create_user, existing_user.username, existing_user.zone)

    def test_create_user(self):
        required_user = IrodsUser("user_1", self.irods_server.users[0].zone)
        user = self.setup_helper.create_user(required_user.username, required_user.zone)
        self.assertEqual(user, required_user)
        user_list = self.setup_helper.run_icommand(["iadmin", "lu"])
        self.assertIn("%s#%s" % (required_user.username, required_user.zone), user_list)

    def test_set_access(self):
        path = self.setup_helper.create_data_object(_DATA_OBJECT_NAME)
        zone = self.irods_server.users[0].zone
        user_1 = self.setup_helper.create_user("user_1", zone)
        user_2 = self.setup_helper.create_user("user_2", zone)

        self.setup_helper.set_access(user_1.username, AccessLevel.READ, path)
        self.setup_helper.set_access(user_2.username, AccessLevel.WRITE, path)

        access_info = self.setup_helper.run_icommand(["ils", "-A", path])
        self.assertIn("%s#%s:read object" % (user_1.username, zone), access_info)
        self.assertIn("%s#%s:modify object" % (user_2.username, zone), access_info)

    def test_get_icat_version(self):
        self.assertEqual(self.setup_helper.get_icat_version(), self.irods_server.version)

    def _assert_metadata_in_retrieved(self, metadata: Metadata, retrieved_metadata: str):
        """
        Assert that the given metadata is in the metadata information retrieved via an `imeta` command.
        :param metadata: the metadata to expect
        :param retrieved_metadata: string representation of metadata, retrieved via an `imeta` command
        """
        for attribute in metadata:
            attribute_values = metadata[attribute]
            if not isinstance(attribute_values, list):
                attribute_values = [attribute_values]

            for value in attribute_values:
                self.assertIn("attribute: %s\nvalue: %s" % (attribute, value), retrieved_metadata)


# Setup tests for all iCAT setups
create_tests_for_all_irods_setups(TestSetupHelper)
for name, value in testwithirods.tests._common.__dict__.items():
    if TestSetupHelper.__name__ in name:
        globals()[name] = value
del TestSetupHelper


if __name__ == "__main__":
    unittest.main()
