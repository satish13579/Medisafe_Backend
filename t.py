import base64
import datetime
str="NDQvNDQvNDQ="
decoded_string = base64.b64decode(str)
#d=encoding.encode_address(decoded_string)
# print(decoded_string.decode())
#print(base64.b64encode(encoding.decode_address("JVM6EULRE7GISC4MF4VP2SVWMCLHBXTXASRHMPI4WA6KTQACCMDKDWAM5U")))

def get_time_diff(date_string):
    date_string = "2023-09-30 15:30:00"
    date_format = "%Y-%m-%d %H:%M:%S"
    date_object = datetime.datetime.strptime(date_string, date_format)
    current_datetime = datetime.datetime.now()
    time_difference = date_object - current_datetime

    days, remainder = divmod(time_difference.seconds, 3600*24)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if date_object>current_datetime:
        if days > 0:
            remaining_time_str = f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds"
        elif hours >0:
            remaining_time_str = f"{hours} hours, {minutes} minutes, {seconds} seconds"
        elif minutes>0:
            remaining_time_str = f"{minutes} minutes, {seconds} seconds"
        elif seconds>0:
            remaining_time_str = f"{seconds} seconds"
        else:
            remaining_time_str = '-'
    else:
        remaining_time_str = '-'

    return remaining_time_str


print(get_time_diff("2023-09-30 19:54:32"))




