"""The harness itself: data is a temporary copy and the network is closed."""
import socket

import pytest


def test_data_files_point_at_temp_copy(app_module):
    root = app_module.DATA_ROOT_FOR_TESTS
    for name in ("ORDERS_FILE", "STP_FILE", "TANKER_REGISTRATIONS_FILE", "OCEMS_API_FILE", "TANKER_DOCUMENT_UPLOAD_FOLDER"):
        assert getattr(app_module, name).startswith(root), name


def test_outbound_network_is_blocked():
    with pytest.raises(OSError):
        socket.create_connection(("93.184.216.34", 443), timeout=1)
