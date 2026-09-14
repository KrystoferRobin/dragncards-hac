import React, { useEffect, useState } from "react";
import { RotatingLines } from "react-loader-spinner";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faStar as faStarO } from "@fortawesome/free-regular-svg-icons";
import { faChevronRight, faStar as faStarS } from "@fortawesome/free-solid-svg-icons";
import moment from "moment";
import { useSiteL10n } from "../../hooks/useSiteL10n";
import { useHistory } from "react-router-dom";
import useProfile from "../../hooks/useProfile";
import { useAuthOptions } from "../../hooks/useAuthOptions";
import Axios from "axios";
import { pluginDisplayAuthor } from "./pluginDisplayAuthor";

const CoverImage = ({ src, className, style, alt = "" }) => {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      style={style}
      onError={() => setFailed(true)}
    />
  );
};

const LogoSlot = ({ src }) => {
  const [failed, setFailed] = useState(!src);
  if (!src || failed) {
    return (
      <div className="relative z-10 flex-shrink-0 flex items-center justify-center px-2">
        <FontAwesomeIcon size="2x" icon={faChevronRight}/>
      </div>
    );
  }
  return (
    <div className="relative z-10 self-stretch aspect-square flex-shrink-0 overflow-hidden my-2 mr-2">
      <img
        src={src}
        alt=""
        className="absolute inset-0 w-full h-full object-contain pointer-events-none"
        onError={() => setFailed(true)}
      />
    </div>
  );
};

export const PluginsTable = ({ plugins, hrefForPlugin }) => {
  const siteL10n = useSiteL10n();
  const history = useHistory();
  const user = useProfile();
  const authOptions = useAuthOptions();

  const [favorites, setFavorites] = useState(
    () => user?.favorite_plugins || {}
  );

  useEffect(() => {
    const loaded = user?.favorite_plugins;
    if (loaded) {
      setFavorites(loaded);
    }
  }, [user?.favorite_plugins]);

  const toggleFavorite = async (pluginId) => {
    const newFavorites = {...favorites};
    if (newFavorites[pluginId]) {
      delete newFavorites[pluginId];
    } else {
      newFavorites[pluginId] = true;
    }
    setFavorites(newFavorites);

    await Axios.post("/be/api/v1/profile/update_favorite_plugins", { favorite_plugins: newFavorites }, authOptions);

    user.setData({
      user_profile: {
        ...user,
        favorite_plugins: newFavorites,
      }
    });
  };

  const isNewPlugin = (createdAt) => {
    if (!createdAt) return false;
    const weekAgo = moment().subtract(7, 'days');
    return moment(createdAt).isAfter(weekAgo);
  };

  const sortedPlugins = plugins ? [...plugins].sort((a, b) => {
    const aFav = favorites[a.id] ? 1 : 0;
    const bFav = favorites[b.id] ? 1 : 0;
    return bFav - aFav;
  }) : plugins;

  return (
        <div className="w-full">
          {plugins == null ?
            <div className="flex justify-center">
              <RotatingLines
                height={100}
                width={100}
                strokeColor="white"/>
            </div>
            :
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {sortedPlugins?.map((plugin) => {
              const isFavorite = !!favorites[plugin.id];
              const bannerUrl = plugin.banner_url;
              const logoUrl = plugin.logo_url;
              return(
                <div
                  key={plugin.id}
                  className="relative min-h-24 w-full flex items-center text-white no-underline select-none rounded-lg overflow-hidden cursor-pointer bg-gray-600-30 hover:bg-red-600-30"
                  onClick={() => history.push(hrefForPlugin ? hrefForPlugin(plugin) : "/plugin/"+plugin.id)}
                >
                  <CoverImage
                    src={bannerUrl}
                    alt=""
                    className="absolute inset-0 w-full h-full object-cover pointer-events-none"
                    style={{ opacity: 0.5 }}
                  />
                  {isNewPlugin(plugin.inserted_at) && (
                    <div className="absolute left-0 top-0 bg-red-600 text-white text-xs font-bold px-2 rounded-br-lg rounded-tl-lg shadow-lg z-10">
                       New
                    </div>
                  )}
                  <div
                    className="relative z-10 flex-1 min-w-0 m-4 pr-1"
                    style={{ textShadow: "0 1px 2px rgba(0,0,0,0.85)" }}
                  >
                    <div className="text-xl inline">
                      {user && <FontAwesomeIcon
                        className="cursor-pointer mr-2"
                        icon={isFavorite ? faStarS : faStarO}
                        style={{color: isFavorite ? "#f59e0b" : "#6b7280"}}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          toggleFavorite(plugin.id);
                        }}
                      />}
                      {plugin.name}
                    </div>
                    <div className="text-xs">{siteL10n("Last update:") + " " + moment.utc(plugin.updated_at).local().format("YYYY-MM-DD HH:mm:ss")}</div>
                    <div className="text-xs">{siteL10n("Author:") + " " + pluginDisplayAuthor(plugin)}</div>
                    <div className="text-xs">{siteL10n("Games in 24hr/30d:") + " " + plugin.count_24hr + "/" + plugin.count_30d}</div>
                  </div>
                  <LogoSlot src={logoUrl} />
                </div>
              )
            })}
            </div>
          }
      </div>
  );
};
export default PluginsTable;
