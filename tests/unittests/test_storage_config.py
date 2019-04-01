# This file is part of curtin. See LICENSE file for copyright and license info.
from .helpers import CiTestCase, skipUnlessJsonSchema
from curtin import storage_config


class TestStorageConfigSchema(CiTestCase):

    @skipUnlessJsonSchema()
    def test_storage_config_schema_is_valid_draft7(self):
        import jsonschema
        schema = storage_config.STORAGE_CONFIG_SCHEMA
        jsonschema.Draft4Validator.check_schema(schema)


# vi: ts=4 expandtab syntax=python
