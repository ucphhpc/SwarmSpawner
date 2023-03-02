class Access:
    @staticmethod
    def allowed(user, image):
        return True
        # if "access" in selected_image:
        #     # Check for static or db users
        #     allowed = False
        #     if self.service_owner in selected_image["access"]:
        #         allowed = True
        #     else:
        #         if os.path.exists(selected_image["access"]):
        #             db_path = selected_image["access"]
        #             try:
        #                 self.log.info(
        #                     "Checking db: {} for "
        #                     "User: {}".format(db_path, self.service_owner)
        #                 )
        #                 with open(db_path, "r") as db:
        #                     users = [user.rstrip("\n").rstrip("\r\n") for user in db]
        #                     if self.service_owner in users:
        #                         allowed = True
        #             except IOError as err:
        #                 self.log.error(
        #                     "User: {} tried to open db file {},"
        #                     "Failed {}".format(self.service_owner, db_path, err)
        #                 )
        #     if not allowed:
        #         self.log.error(
        #             "User: {} tried to launch {} without access".format(
        #                 self.service_owner, selected_image["image"]
        #             )
        #         )
        #         raise Exception("You don't have permission to launch that image")
