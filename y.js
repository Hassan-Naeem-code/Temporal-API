import { ProgressBar } from "react-bootstrap";
import { toast } from "react-toastify";
import { FaChevronDown, FaChevronUp } from "react-icons/fa";
import moment from "moment";
import Button from "src/components/common/Button";
import Styles from "./styles.module.scss";
import "./Campaign.css";

const CampaignInfo = ({
  info,
  index,
  tabIndex,
  changeCurrentCampaignStatus,
  navigate,
  openIndex,
  setOpenIndex,
  setSelectedCampaignInfoForPublishing,
  toggleCampaignPublishPopup,
  campaignTransactionPointsInfo,
  setCampaignPublishPopup,
  user,
}) => {
  const handleToggle = (index: number) => {
    setOpenIndex(openIndex === index ? null : index);
  };
  const campaignStatus = [];
  if (info?.status == "Resumed") {
    campaignStatus?.push({
      name: "Pause",
    });
  }
  if (info?.status == "Archive") {
    campaignStatus?.push({
      name: "Pending",
    });
  }
  if (info?.status == "Pause") {
    campaignStatus?.push({
      name: "Resumed",
    });
  }
  if (info?.status == "Published") {
    // campaignStatus?.push({
    //   name: "Resumed",
    // });
    campaignStatus?.push({
      name: "Pause",
    });
  }
  const colorStatus = {
    Active: "c-primary",
    Pending: "c-yellow",
    Completed: "c-secondary",
    Pause: "c-black",
  };

  const calculatePercentageUsed = (
    amountSpent: number,
    planBudget: number
  ): number => {
    const percentageUsed = amountSpent / planBudget;
    return Math.min(Math.round(percentageUsed), 100);
  };

  const calculatePercentage = (startDate, endDate, status) => {
    if (status != "Published") return 0;

    const startDateTime = moment(startDate);
    const endDateTime = moment(endDate);
    const presentDateTime = moment();

    // Calculate total number of days
    const totalDays = endDateTime.diff(startDateTime, "days");

    // Calculate number of days passed from start date to present date
    const daysPassed = presentDateTime.diff(startDateTime, "days");

    // Days left
    const daysLeft = endDateTime.diff(presentDateTime, "days");

    // if startDate has days left then just return 0.
    if (presentDateTime.isBefore(startDateTime)) {
      return 0;
    } else if (presentDateTime.isAfter(endDateTime)) {
      // Campaign Ended
      return 100;
    } else if (presentDateTime.isSame(endDateTime, "day")) {
      return 100;
    } else {
      // Present date is between start and end date
      return Math.round((daysPassed / totalDays) * 100);
    }
  };

  const calculateDays = (startDate, endDate, showProgress = false) => {
    const startDateTime = moment(startDate);
    const endDateTime = moment(endDate);
    const presentDateTime = moment();

    // Calculate total number of days
    const totalDays = endDateTime.diff(startDateTime, "days");

    // Calculate number of days passed from start date to present date
    const daysPassed = presentDateTime.diff(startDateTime, "days");

    // Days left
    const daysLeft = endDateTime.diff(presentDateTime, "days");

    // if startDate has days left then just return empty string.
    if (presentDateTime.isBefore(startDateTime)) {
      return "";
    } else if (presentDateTime.isAfter(endDateTime)) {
      // Campaign Ended
      return "";
    } else if (presentDateTime.isSame(endDateTime, "day")) {
      return "";
    } else {
      // Present date is between start and end date
      return `${daysLeft} days left`;
    }
  };

  const progressBarColor = (startDate, endDate, status) => {
    if (calculatePercentage(startDate, endDate, status) == 100) {
      return "completedClass";
    } else return "yellow";
  };

  const dynamicButtonLabels = (info) => {
    if (
      calculatePercentage(
        info?.plan?.schedule?.startDate,
        info?.plan?.schedule?.endDate,
        info?.status
      ) === 100
    ) {
      return "Completed";
    } else if (info?.status == "Published") {
      return "Archive";
    } else if (info?.status == "Resumed") {
      return "Archive";
    } else if (info?.status == "Pause") {
      return "Archive";
    } else {
      return "Publish";
    }
  };

  const daysDifference = (date: any) => {
    if (!!date) {
      const startDate = new Date(date);
      const currentDate = new Date();

      const differenceInTime = currentDate?.getTime() - startDate?.getTime();
      const differenceInDays = Math.floor(
        Math.abs(differenceInTime / (1000 * 3600 * 24))
      );

      return differenceInDays;
    }
  };
  const changeCampaignStatus = (id, campaignStatus) => {
    // if business has logo then allow to publish
    if (!user?.business?.logo) {
      toast.error("Please upload business logo first.");
      return;
    }

    if (
      campaignStatus !== "" &&
      String(campaignStatus)?.toLowerCase() ==
        String(info?.status)?.toLowerCase()
    )
      return toast.error("Please select other status to change");
    if (
      campaignStatus !== "" &&
      String(campaignStatus)?.toLowerCase() !== "published"
    ) {
      changeCurrentCampaignStatus(id, campaignStatus);
    } else if (
      campaignStatus !== "" &&
      String(campaignStatus)?.toLowerCase() !==
        String(info?.status)?.toLowerCase()
    ) {
      const currentDate = new Date();
      const campaignEndDate = new Date(info?.plan?.schedule?.endDate);
      const currentDateMilliSeconds = currentDate?.getTime();
      const campaignEndDateMilliSeconds = campaignEndDate?.getTime();
      if (campaignEndDateMilliSeconds >= currentDateMilliSeconds) {
        // changeCurrentCampaignStatus(id, campaignStatus);
        setSelectedCampaignInfoForPublishing({
          id,
          campaignStatus,
          info,
        });
        toggleCampaignPublishPopup();
      } else {
        return toast.error(
          "Please Update The End Date To Publish The Campaign"
        );
      }
    }
  };
  const navigateToDetails = (id) => {
    navigate(`/campaign/detail/${id}`);
    // window.location.reload();
  };
  const checkPointsAvailableThenPublish = () => {
    switch (info?.status) {
      case "Published":
      case "Resumed":
      case "Pause":
        refundCampaign();
        break;
      case "Pending":
        publishCampaign();
        break;
      default:
        alert("Default case");
    }
  };
  const refundCampaign = () => {
    console.log("refundCampaign");
    toggleCampaignPublishPopup()
  };
  const publishCampaign = () => {
    if (user?.role_code == "ADMIN") {
      if (
        Number(campaignTransactionPointsInfo?.points) >=
        Number(info?.plan?.budget) * 100
      ) {
        changeCampaignStatus(info?._id, "Published");
      } else {
        setCampaignPublishPopup(true);
        return toast.error("Don't have enough points to publish the campaign");
      }
    } else if (user?.role_code == "USER") {
      if (
        Number(campaignTransactionPointsInfo?.pointsToReedem) >=
        Number(info?.plan?.budget) * 100
      ) {
        changeCampaignStatus(info?._id, "Published");
      } else {
        setCampaignPublishPopup(true);
        return toast.error("Don't have enough points to publish the campaign");
      }
    }
  };
  return (
    <>
      <tr key={`campaign-row-${index + 1}`}>
        <td
          onClick={() => navigateToDetails(info?._id)}
          className="cursor-pointer"
        >
          <h4>{info?.plan?.campaignName}</h4>
          <div className="d-flex align-items-center f12 graphik-light c-gray">
            <span className="me-2">
              {moment(info?.plan?.schedule?.startDate).format("YYYY MMM DD")}
            </span>
            <span className="me-2">-</span>
            <span className="me-2">
              {moment(info?.plan?.schedule?.endDate).format("YYYY MMM DD")}
            </span>
          </div>
        </td>
        <td>
          <h4 className={`${info?.status} f20 graphik-medium`}>
            {calculatePercentage(
              info?.plan?.schedule?.startDate,
              info?.plan?.schedule?.endDate,
              info?.status
            ) === 100 ? (
              <span className={`${Styles.text_completed}`}>Completed</span>
            ) : tabIndex == 0 ? (
              <select
                name="campaign_status_dropdown"
                className={`campaign_dropdown ${colorStatus[info?.status]}`}
                onChange={(e) =>
                  changeCampaignStatus(info?._id, e.target.value)
                }
              >
                <option value="">{info?.status}</option>
                {campaignStatus?.map((status, index) => {
                  return (
                    <option
                      value={status?.name}
                      key={`camapign-option-status-${index}`}
                    >
                      {status?.name}
                    </option>
                  );
                })}
              </select>
            ) : calculatePercentage(
                info?.plan?.schedule?.startDate,
                info?.plan?.schedule?.endDate,
                info?.status
              ) === 100 ? (
              <span className={`${Styles.text_completed}`}>Completed</span>
            ) : (
              info?.status
            )}
          </h4>
        </td>
        <td>
          <div className="progress-text d-flex align-items-center justify-content-between">
            <p>{`$ 0 out of $ ${info?.plan?.budget} Budget`}</p>
            {/* <p>{`${daysDifference(info?.plan?.schedule?.endDate)} days left`}</p> */}
            <p>{`${calculateDays(
              info?.plan?.schedule?.startDate,
              info?.plan?.schedule?.endDate
            )}`}</p>
          </div>
          <div>
            <ProgressBar
              variant={progressBarColor(
                info?.plan?.schedule?.startDate,
                info?.plan?.schedule?.endDate,
                info?.status
              )}
              className={`bg_completed`}
              now={calculatePercentage(
                info?.plan?.schedule?.startDate,
                info?.plan?.schedule?.endDate,
                info?.status
              )}
              max={100}
              role="progressbar"
            ></ProgressBar>
          </div>
        </td>
        <td className="text-center">
          <h4>{info?.impression}</h4>
        </td>
        <td className="text-center">
          <h4>{info?.reach}</h4>
        </td>
        <td className="text-center">
          <h4>{info?.click}</h4>
        </td>
        <td>
          <Button
            variant="filled"
            label={dynamicButtonLabels(info)}
            color={
              calculatePercentage(
                info?.plan?.schedule?.startDate,
                info?.plan?.schedule?.endDate,
                info?.status
              ) === 100
                ? "saveBtn"
                : "primary"
            }
            size="medium"
            type="button"
            onClick={() => checkPointsAvailableThenPublish()}
          />
        </td>
        <td>
          {info?.campaignGroupId ? (
            openIndex >= 0 && openIndex === index ? (
              <FaChevronUp onClick={() => handleToggle(index)} />
            ) : (
              <FaChevronDown onClick={() => handleToggle(index)} />
            )
          ) : null}
        </td>
      </tr>
    </>
  );
};

export default CampaignInfo;
