package list.community.service;

import list.community.dto.DcPost;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class DcBestService {

    private static final String URL = "https://gall.dcinside.com/board/lists?id=dcbest";

    public List<DcPost> getTop10Posts(){
         List<DcPost> posts = new ArrayList<>();

         try {
             Document doc = Jsoup.connect(URL)
                     .userAgent("Mozilla/5.0")
                     .referrer("https://www.google.com")
                     .timeout(10000)
                     .get();

             Elements rows = doc.select("tr.ub-content.us-post");

             int count = 0;
             for (Element row : rows) {
                 if(count >= 10) break;
                 String title = row.select("td.gall_tit.ub-word").text();
                 String writer = row.select("td.gall_writer").attr("data-nick");
                 String date = row.select("td.gall_date").attr("title");
                 String views = row.select("td.gall_count").text();
                 String likes = row.select("td.gall_recommend").text();

                 posts.add(new DcPost(title, views, likes));
                 count++;

             }
         } catch (Exception e) {
             e.printStackTrace();
         }

         return posts;
    }

}
