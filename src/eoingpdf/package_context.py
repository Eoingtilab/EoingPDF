"""Windows package identity helpers used by Microsoft Store builds."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

APPMODEL_ERROR_NO_PACKAGE = 15700
ERROR_INSUFFICIENT_BUFFER = 122


def package_full_name() -> str | None:
	"""Return the current MSIX package full name, or None for unpackaged builds."""
	override = os.environ.get('EOINGPDF_TEST_PACKAGE_FULL_NAME')
	if override is not None:
		return override or None
	if os.name != 'nt':
		return None
	length = wintypes.UINT(0)
	try:
		get_name = ctypes.windll.kernel32.GetCurrentPackageFullName
	except AttributeError:
		return None
	result = get_name(ctypes.byref(length), None)
	if result == APPMODEL_ERROR_NO_PACKAGE:
		return None
	if result != ERROR_INSUFFICIENT_BUFFER or not length.value:
		return None
	buffer = ctypes.create_unicode_buffer(length.value)
	result = get_name(ctypes.byref(length), buffer)
	return buffer.value if result == 0 and buffer.value else None


def is_packaged() -> bool:
	return package_full_name() is not None


def store_managed_updates() -> bool:
	"""Microsoft Store MSIX builds must let the Store own package replacement."""
	return is_packaged()
