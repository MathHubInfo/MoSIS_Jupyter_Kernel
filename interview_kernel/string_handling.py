#!/usr/bin/env python3

from distutils.util import strtobool
import re
from urllib.parse import urlparse, urlencode, ParseResult

object_delimiter = "❘"

def means_no(answer):
    try:
        ret = strtobool(answer)
        if ret == False:
            return True
    except ValueError:
        return False
    return False

def build_url(baseurl, path, args_dict={}, query_dict={}):
    # Returns a list in the structure of urlparse.ParseResult
    url = urlparse(baseurl)
    # construct new parseresult
    new_url = ParseResult(url.scheme, url.netloc, path, "", urlencode(args_dict),  # todo urlencode
                          # urlencode(query_dict, doseq=True),
                           url.fragment)
    return new_url.geturl()

# cf. https://stackoverflow.com/questions/14962485/finding-a-key-recursively-in-a-dictionary
def get_recursively(search_dict, field):
    """
    Takes a dict with nested lists and dicts, and searches all dicts for a key of the field provided,
    returning a list of the values.
    """
    fields_found = []
    for key, value in search_dict.items():
        if key == field:
            fields_found.append(value)
        elif isinstance(value, dict):
            results = get_recursively(value, field)
            for result in results:
                fields_found.append(result)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    more_results = get_recursively(item, field)
                    for another_result in more_results:
                        fields_found.append(another_result)
    return fields_found

def get_first_key(ordered_dict):
    return list(ordered_dict.keys())[0]

# """string modification functions"""
def insert_type(string, whichtype):
    eqidx = string.find("=")
    if eqidx < 0:
        raise Exception
    if not self.has_colon(string):
        # print('has no colon ' + equidx)
        return string[:eqidx] + " : " + whichtype + " " + object_delimiter + " " + string[eqidx:]
    return string[:eqidx] + " " + object_delimiter + " " + string[eqidx:]


def type_is_function_from(type_string, from_string):
    if type_string.startswith(from_string + " →"):
        return True
    if type_string.startswith("{ : " + from_string):
        return True

    from_string = make_list_of_type_symbols(from_string)
    type_string = make_list_of_type_symbols(type_string)

    if len(from_string) > len(type_string):
        return False

    for index in range(len(from_string)):
        if from_string[index] != type_string[index]:
            return False

    return True


def type_is_function_to(type_string, to_string):
    if type_string.endswith("→ " + to_string):
        return True
    if type_string.endswith("} " + to_string):
        return True
    to_string = make_reverse_list_of_type_symbols(to_string)
    type_string = make_reverse_list_of_type_symbols(type_string)

    if len(to_string) > len(type_string):
        return False

    for index in range(len(to_string)):
        if to_string[index] != type_string[index]:
            return False

    return True


def remove_apply_brackets(string):
    return string.split('(', 1)[0] + string.split(')', 1)[1].strip()


def insert_before_def(string, insertstring):
    eqidx = string.find("=")
    if eqidx < 0:
        raise Exception
    return string[:eqidx + 1] + " " + insertstring + " " + string[eqidx + 1:]


def get_first_word(string):
    return re.split('\W+', string, 1)[0]


def get_last_type(string):
    string = remove_round_brackets(string)
    string = string.rstrip()
    return re.split('[→ \s]', string)[-1]


def make_reverse_list_of_type_symbols(string):
    slist = make_list_of_type_symbols(string)
    slist.reverse()
    return slist


def make_list_of_type_symbols(string):
    string = remove_arrows(remove_colons(remove_curly_brackets(remove_round_brackets(string))))
    slist = string.split(' ')
    slist = list(filter(lambda a: a != '', slist))
    return slist


def remove_round_brackets(string):
    return string.replace(")", "").replace("(", "")


def remove_curly_brackets(string):
    return string.replace("{", "").replace("}", "")


def remove_arrows(string):
    return string.replace("→", "")


def remove_colons(string):
    return string.replace(":", "")


def has_equals(string):
    if "=" in string:
        return True
    return False


def has_colon(string):
    if ":" in string:
        return True
    return False


def eq_to_doteq(string):
    return string.replace("=", "≐")


def assert_question_mark(what):
    if "?" not in what:
        return "?" + what
    else:
        return what


def add_ods(string):
    objects = re.split(r'(\W)', string)
    onedel = False
    for i in range(2, len(objects)):
        if bool(re.match('[:=]', objects[i], re.I)):  # if it starts with : or =
            if onedel:
                objects[i] = object_delimiter + objects[i]
                return ''.join(objects)
            onedel = True  # start only at second : or =
    return ''.join(objects)


def functionize(string, typename="Ω", varname="x"):
    return string.replace("=", "= [ " + varname + " : " + typename + "]")

def split_string_at_AS(string):
    return re.split('AS', string)