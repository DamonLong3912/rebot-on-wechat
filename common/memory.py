from common.expired_dict import ExpiredDict

USER_IMAGE_CACHE = ExpiredDict(60 * 3)


OIL_INQUIRY_CACHE = ExpiredDict(60 * 60)
USER_FILE_CACHE = ExpiredDict(60 * 3)
USER_URL_CACHE = ExpiredDict(60 * 3)