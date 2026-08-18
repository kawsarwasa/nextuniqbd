# Product image upload deployment

The Django product form enforces a 3 MiB (3,145,728-byte) limit for each image, a maximum of four images, and a 2-megapixel image limit. The largest normal multipart request is therefore about 12 MiB plus ordinary form fields.

No PHP setting applies to this Django application. `FILE_UPLOAD_MAX_MEMORY_SIZE` must not be used as a rejection limit; it only determines when Django moves an upload from memory to a temporary file.

If the cPanel Apache virtual host has a restrictive `LimitRequestBody`, ask the hosting provider to set it to at least 16 MiB (`16777216`) for the Passenger application path. Apache's default is unlimited, so no change is needed unless the host has configured a lower limit. Passenger forwards the request to Django after Apache accepts it.
