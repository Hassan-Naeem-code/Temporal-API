import { useState, useEffect, useRef } from "react";
import * as lodash from "lodash";
import globalStyles from "src/global.module.scss";
import Styles from "./styles.module.scss";
import RenderAvatar from "../common/RenderAvatar";
import { HiMiniXMark } from "react-icons/hi2";
import { useAuth } from "src/hooks/form/useAuth";
import { useSearch } from "src/hooks/form/useSearch";
import Skeleton from "react-loading-skeleton";
interface ISearchAndSelectUserInput {
  endPoint: string;
  searchField: string;
  resultArray?: any[];
  setResultArray?: any;
  customClass?: string;
  showSelected?: boolean;
  label?: string;
  placeholder?: string;
  varaint?: "borderless" | "round" | "directMessage";
  layoutType?: "hideDropdown" | "normal"
  inpLengthChk?: boolean;
  setInpLength?: any;
  selectMultiple?: boolean;
  disable?: boolean;
}

const SearchAndSelectUserInput = ({
  endPoint,
  searchField,
  resultArray,
  disable,
  setResultArray,
  customClass,
  showSelected = false,
  layoutType = 'normal',
  inpLengthChk = false,
  setInpLength,
  selectMultiple = true,
  ...props
}: ISearchAndSelectUserInput) => {
  const [query, setQuery] = useState("");
  const {
    store: { user },
  } = useAuth(null);

  const { searchInTypesense, store: { searchResult, status: searchStatus } } = useSearch()

  useEffect(() => {
    const handleSearch = async () => {
      const text = query.trim();
      if (inpLengthChk) {
        setInpLength(text.length);
      }
      if (text.length >= 3) {
        const body = {
          query: text,
          query_by: searchField,
          filtered_by: `businessId:${user?.businessId}`,
        };
        await searchInTypesense({ endPoint, body })
      }
    };
    const debounceHandleSearch = lodash.debounce(handleSearch, 1200);
    debounceHandleSearch();
  }, [query, searchField]);

  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);
  };

  const selectOption = (option) => {
    setQuery("");
    if (!selectMultiple && resultArray.length) return;
    const isAlreadySelected = resultArray.some(
      (ele) => ele._id === option.document._id
    );
    if (isAlreadySelected) return;
    setResultArray([...resultArray, option.document]);
    // setResArr([]);// Hassaan naeem please check this, this cause the build error.
    
  };

  const divRef = useRef(null);
  const [showDropdown, setShowDropdown] = useState(false);

  useEffect(() => {
    const handleDocumentClick = (event) => {
      if (divRef.current && !divRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("click", handleDocumentClick);

    return () => {
      document.removeEventListener("click", handleDocumentClick);
    };
  }, []);

  const removeUser = (user) => {
    const filteredUsers = resultArray?.filter((selUser) => selUser !== user);
    setResultArray([...filteredUsers]);
  };

  return (
    <div
      ref={divRef}
      className={`${Styles.searchComp_main} ${Styles[props?.varaint]} ${
        Styles[customClass]
      }`}
    >
      {props.label && <label htmlFor="searchInput">{props.label}</label>}

      <input
        id={"searchInput"}
        style={{
          // borderRadius: "10px",
          marginTop: "0px",
          borderColor: "rgb(0 0 0 / 50%)",
        }}
        type="text"
        placeholder={props.placeholder ? props.placeholder : "Search"}
        value={query}
        disabled={disable}
        onChange={handleInputChange}
        onFocus={() => setShowDropdown(true)}
      />
      {showDropdown && searchResult?.length && layoutType !== "hideDropdown" ? (
        <ul
          className={`${globalStyles.cardboxshadowqa} ${Styles.searchComp_results}`}
        >
          {searchResult?.map((res, index) => {
            return (
              <li
                key={index}
                className="my-1 cursor-pointer f20 dflexCenter gap-2"
                onClick={() => selectOption(res)}
              >
                <RenderAvatar
                  image={res.document?.profilePicUrl}
                  name={`${res.document?.firstName} ${res.document?.lastName}`}
                  varaint="round"
                  size="x-small"
                />
                <span className="f16">{res.document[searchField]}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        ""
      )}


     {showDropdown && !searchResult?.length && query?.length ? (
        <div
          className={`${globalStyles.cardboxshadowqa}  ${Styles.searchComp_results}`}
        >
          {
            searchStatus === 'pending' ?
              <>
                <div className='mt-3 mb-3 w-100'>
                  <Skeleton height={20} />
                </div>
                <div className='mt-3 mb-3 w-100'>
                  <Skeleton height={20} />
                </div>
              </>
              :
              <span>No search results...</span>
          }
        </div>
      ) : (
        ""
      )}
      {showSelected && resultArray?.length ? (
        <div className="dflexCenter gap-2 mt-3">
          {resultArray.map((user) => (
            <div
              key={user._id}
              className={`${Styles.selectedUser_avatarMain} dflexCenter gap-1 flex-column`}
            >
              <span onClick={() => removeUser(user)} className="cursor-pointer">
                {" "}
                <HiMiniXMark />{" "}
              </span>
              <RenderAvatar
                image={user?.profilePicUrl}
                name={`${user?.firstName} ${user?.lastName}`}
                varaint="round"
                size="small"
              />
              <p className="f16 text-center oneline-text">
                {" "}
                {user?.firstName} {user?.lastName}{" "}
              </p>
            </div>
          ))}
        </div>
      ) : (
        ""
      )}
    </div>
  );
};

export default SearchAndSelectUserInput;