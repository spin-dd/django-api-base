import zipfile
from io import BytesIO

from django.core import serializers
from django.core.files.base import ContentFile


class Zipball:
    def __init__(self):
        self.in_memory_zip = BytesIO()

    def append(self, filename_in_zip, file_contents):
        # Get a handle to the in-memory zip in append mode
        zf = zipfile.ZipFile(self.in_memory_zip, "a", zipfile.ZIP_DEFLATED, False)

        # Write the file to the in-memory zip
        zf.writestr(filename_in_zip, file_contents)

        # Mark the files as having been created on Windows so that
        # Unix permissions are not inferred as 0000
        for zfile in zf.filelist:
            zfile.create_system = 0

        return self

    def read(self):
        """Returns a string with the contents of the in-memory zip."""
        self.in_memory_zip.seek(0)
        return self.in_memory_zip.read()

    def write_to(self, stream):
        stream.write(self.read())

    def write_to_file(self, filename):
        """Writes the in-memory zip to a file."""
        f = open(filename, "wb")
        f.write(self.read())
        f.close()

    def to_contentfile(self):
        return ContentFile(self.read())


class ModelZipball(Zipball):
    def append_query(self, queryset):
        file_name = f"{queryset.model._meta.app_label}.{queryset.model._meta.model_name}.json"
        return self.append(file_name, serializers.serialize("json", queryset))
