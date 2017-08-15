from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from univention.admin import localization
from univention.testing.umc_selenium.base import UMCSeleniumTest
import time
import univention.testing.strings as uts

translator = localization.translation('univention-ucs-test_umc-tests')
_ = translator.translate


class UDMBase(UMCSeleniumTest):

	def __init__(self, *args, **kwargs):
		super(UDMBase, self).__init__(*args, **kwargs)


class Users(object):

	def __init__(self, selenium):
		self.selenium = selenium

	def open_details(self, username):
		xpath = '//input[@name="objectPropertyValue"]'
		elems = webdriver.support.ui.WebDriverWait(xpath, 60).until(
			self.selenium.get_all_enabled_elements
		)
		elems[0].clear()
		elems[0].send_keys(username)
		elems[0].send_keys(Keys.RETURN)
		time.sleep(5)
		self.selenium.wait_until_all_standby_animations_disappeared()

		self.selenium.click_grid_entry(username)
		self.selenium.wait_for_text(_('User name'))

	def close_details(self):
		self.selenium.click_button(_('Back'))
		self.wait_for_main_grid_load()

	def get_primary_mail(self):
		xpath = '//input[@name="mailPrimaryAddress"]'
		elems = webdriver.support.ui.WebDriverWait(xpath, 60).until(
			self.selenium.get_all_enabled_elements
		)
		return elems[0].get_attribute('value')

	def wait_for_main_grid_load(self):
		pass

	def add_user(
		self,
		template=None,
		firstname='',
		lastname=None,
		username=None,
		password='univention'
	):
		if username is None:
			username = uts.random_string()
		if lastname is None:
			lastname = uts.random_string()

		self.selenium.click_button(_('Add'))

		if template is not None:
			self.selenium.wait_for_text(_("User template"))
			template_selection_dropdown_button = self.selenium.driver.find_element_by_xpath(
				'//input[@name="objectTemplate"]/../..//input[contains(concat(" ", normalize-space(@class), " "), " dijitArrowButtonInner ")]'
			)
			template_selection_dropdown_button.click()
			self.selenium.click_text(template)
			self.selenium.click_button(_("Next"))

		self.selenium.wait_for_text(_("First name"))
		self.selenium.enter_input("firstname", firstname)
		self.selenium.enter_input("lastname", lastname)
		self.selenium.enter_input("username", username)

		self.selenium.click_button(_("Next"))
		self.selenium.wait_for_text(_("Password *"))
		self.selenium.enter_input("password_1", password)
		self.selenium.enter_input("password_2", password)
		self.selenium.click_button(_("Create user"))
		self.selenium.wait_for_text(_('has been created'))
		self.selenium.click_button(_('Cancel'))
		self.selenium.wait_until_all_dialogues_closed()

		return username